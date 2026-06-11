"use strict";

var EditorScreen = {
    _lesson:     null,
    _lessonId:   null,
    _stepIdx:    0,
    _collapsed:  {},

    onEnter: function(data) {
        if (data && data.lessonId && data.lessonId !== this._lessonId) {
            this._lessonId = data.lessonId;
            this._stepIdx  = 0;
            sendToPython("loadLesson", { lessonId: data.lessonId });
        } else if (this._lesson) {
            this._render();
        }
    },

    onLessonLoaded: function(lessonId, lesson) {
        this._lessonId = lessonId;
        this._lesson   = lesson || { id: lessonId, title: "", steps: [], solution_code: "" };
        this._stepIdx  = Math.min(this._stepIdx, Math.max(0, (this._lesson.steps || []).length - 1));
        sendToPython("setCurrentLesson", { lessonId: lessonId, stepIndex: this._stepIdx });
        var firstStep = (this._lesson.steps || [])[this._stepIdx];
        if (firstStep) {
            sendToPython("setEditorStep", {
                stepId:      firstStep.id,
                rawTs:       firstStep.raw_ts    || "",
                cachedXml:   firstStep.cached_xml || "",
                lessonTitle: this._lesson.title || "Lesson",
            });
        } else {
            sendToPython("setEditorStep", {
                stepId:      "_blank_",
                rawTs:       "",
                cachedXml:   "",
                lessonTitle: this._lesson.title || "Lesson",
            });
        }
        this._render();
    },

    onPublished: function(lessonId, classroomId) {
        this._showToast("Published to classroom.");
    },

    _render: function() {
        this._renderLessonList();
        this._renderStepList();
        this._renderStepFields();
    },

    _renderLessonList: function() {
        var el = document.getElementById("editor-lesson-list");
        if (!el) return;
        var current = this._lessonId;
        el.innerHTML = State.lessons.map(function(d) {
            var active = d.id === current ? " active" : "";
            return [
                '<div class="step-item' + active + '" onclick="EditorScreen._switchLesson(' + _attr(d.id) + ')">',
                '<div class="step-number"></div>',
                '<div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + EditorScreen._esc(d.title || "Untitled") + "</div>",
                "</div>",
            ].join("");
        }).join("");
    },

    _renderStepList: function() {
        var el = document.getElementById("editor-step-list");
        if (!el || !this._lesson) return;
        var steps   = this._lesson.steps || [];
        var current = this._stepIdx;
        el.innerHTML = steps.map(function(step, i) {
            var active = i === current ? " active" : "";
            return [
                '<div class="step-item' + active + '" onclick="EditorScreen._selectStep(' + i + ')">',
                '<div class="step-number">' + (i + 1) + "</div>",
                '<div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + EditorScreen._esc(step.name || "Step " + (i + 1)) + "</div>",
                "</div>",
            ].join("");
        }).join("");
    },

    _renderStepFields: function() {
        var lesson = this._lesson;
        if (!lesson) return;
        var steps = lesson.steps || [];
        var step  = steps[this._stepIdx] || null;

        var titleEl        = document.getElementById("step-title");
        var instructionsEl = document.getElementById("step-instructions");
        var hintEl         = document.getElementById("step-hint");
        var codePreviewEl  = document.getElementById("step-code-preview");

        if (titleEl)        titleEl.value        = step ? (step.name        || "") : "";
        if (instructionsEl) instructionsEl.value = step ? (step.description || "") : "";
        if (hintEl)         hintEl.value         = step ? (step.hint        || "") : "";
        if (codePreviewEl)  codePreviewEl.textContent = step ? (step.raw_ts || "(auto-saved as you type)") : "";

        var noStepMsg  = document.getElementById("no-step-msg");
        var stepEditor = document.getElementById("step-editor-fields");
        if (noStepMsg)  noStepMsg.style.display  = steps.length === 0 ? "" : "none";
        if (stepEditor) stepEditor.style.display = steps.length === 0 ? "none" : "";
    },

    _selectStep: function(idx) {
        this._flushCurrentStepFields();
        this._stepIdx = idx;
        this._renderStepList();
        this._renderStepFields();
        var step = (this._lesson.steps || [])[idx];
        if (step) {
            sendToPython("setEditorStep", {
                stepId:      step.id,
                rawTs:       step.raw_ts    || "",
                cachedXml:   step.cached_xml || "",
                lessonTitle: this._lesson ? (this._lesson.title || "Lesson") : "Lesson",
            });
        }
    },

    _addStep: function() {
        if (!this._lesson) return;
        var steps         = this._lesson.steps || [];
        var prevRawTs     = steps.length > 0 ? (steps[steps.length - 1].raw_ts     || "") : "";
        var prevCachedXml = steps.length > 0 ? (steps[steps.length - 1].cached_xml || "") : "";
        var newIdx        = steps.length;
        steps.push({
            id:          "step_" + (newIdx + 1),
            order:       newIdx + 1,
            name:        "",
            description: "",
            hint:        "",
            raw_ts:      prevRawTs,
            cached_xml:  prevCachedXml,
        });
        this._lesson.steps = steps;
        this._saveLesson();
        this._stepIdx = newIdx;
        this._render();
        sendToPython("setEditorStep", {
            stepId:      steps[newIdx].id,
            rawTs:       prevRawTs,
            cachedXml:   prevCachedXml,
            lessonTitle: this._lesson.title || "Lesson",
        });
    },

    _deleteStep: function(idx) {
        if (!this._lesson) return;
        var steps = this._lesson.steps || [];
        if (steps.length === 0) return;
        steps.splice(idx, 1);
        steps.forEach(function(s, i) { s.order = i + 1; });
        this._lesson.steps = steps;
        this._stepIdx      = Math.min(this._stepIdx, Math.max(0, steps.length - 1));
        this._saveLesson();
        this._render();
        var step = steps[this._stepIdx];
        if (step) {
            sendToPython("setEditorStep", {
                stepId:      step.id,
                rawTs:       step.raw_ts    || "",
                cachedXml:   step.cached_xml || "",
                lessonTitle: this._lesson ? (this._lesson.title || "Lesson") : "Lesson",
            });
        }
    },

    _moveStep: function(idx, direction) {
        var steps  = this._lesson.steps || [];
        var target = idx + direction;
        if (target < 0 || target >= steps.length) return;
        var tmp       = steps[idx];
        steps[idx]    = steps[target];
        steps[target] = tmp;
        steps.forEach(function(s, i) { s.order = i + 1; });
        this._lesson.steps = steps;
        this._stepIdx      = target;
        this._saveLesson();
        this._render();
    },

    _switchLesson: function(lessonId) {
        if (lessonId === this._lessonId) return;
        this._flushCurrentStepFields();
        this._saveLesson();
        this._stepIdx  = 0;
        this._lessonId = lessonId;
        sendToPython("loadLesson", { lessonId: lessonId });
    },

    _flushCurrentStepFields: function() {
        if (!this._lesson) return;
        var steps = this._lesson.steps || [];
        var step  = steps[this._stepIdx];
        if (!step) return;
        var titleEl        = document.getElementById("step-title");
        var instructionsEl = document.getElementById("step-instructions");
        var hintEl         = document.getElementById("step-hint");
        if (titleEl)        step.name        = titleEl.value;
        if (instructionsEl) step.description = instructionsEl.value;
        if (hintEl)         step.hint        = hintEl.value;
    },

    _saveLesson: function() {
        if (!this._lesson || !this._lessonId) return;
        this._flushCurrentStepFields();
        sendToPython("saveLesson", { lessonId: this._lessonId, lesson: this._lesson });
    },

    _publishDialog: function() {
        if (!this._lessonId || !this._lesson) return;
        var classroom = State.activeClassroom || State.classrooms[0];
        if (!classroom) {
            ConfirmDialog.show("No classrooms available.", "OK", "btn-secondary", null);
            return;
        }
        var self = this;
        ConfirmDialog.show(
            'Publish "' + this._esc(this._lesson.title || "this lesson") + '" to ' + this._esc(classroom.name || classroom.id) + "?",
            "Publish", "btn-success",
            function(ok) {
                if (!ok) return;
                self._flushCurrentStepFields();
                var steps = self._lesson.steps || [];
                if (steps.length > 0)
                    self._lesson.solution_code = steps[steps.length - 1].raw_ts || "";
                sendToPython("publishLesson", {
                    lessonId:    self._lessonId,
                    classroomId: classroom.id,
                    lesson:      self._lesson,
                });
            }
        );
    },

    _deleteLesson: function() {
        if (!this._lessonId) return;
        ConfirmDialog.show("Move this lesson to the recycle bin?", "Move to Bin", "btn-danger", function(ok) {
            if (ok) sendToPython("deleteLesson", { lessonId: EditorScreen._lessonId });
        });
    },

    _promptBack: function() {
        if (!this._lesson) {
            navigate("classroom", { classroomId: State.activeClassroom && State.activeClassroom.id });
            return;
        }
        var lessonId = this._lessonId;
        var entry = State.lessons.find(function(d) { return d.id === lessonId; });
        var isPublished =
            (entry && Array.isArray(entry.published_to) && entry.published_to.length > 0) ||
            State.classrooms.some(function(c) {
                return (c.enabled_lessons || []).indexOf(lessonId) !== -1;
            });
        if (isPublished) {
            navigate("classroom", { classroomId: State.activeClassroom && State.activeClassroom.id });
            return;
        }
        document.getElementById("dialog-save-back").classList.remove("hidden");
    },

    _confirmBack: function(save) {
        document.getElementById("dialog-save-back").classList.add("hidden");
        if (save) this._saveLesson();
        navigate("classroom", { classroomId: State.activeClassroom && State.activeClassroom.id });
    },

    _previewLesson: function() {
        if (!this._lessonId || !this._lesson) return;
        this._flushCurrentStepFields();
        sendToPython("previewLesson", { lessonId: this._lessonId, lesson: this._lesson });
    },

    _toggleSection: function(id) {
        var section = document.getElementById(id);
        if (!section) return;
        section.classList.toggle("collapsed");
        this._collapsed[id] = section.classList.contains("collapsed");
    },

    _showToast: function(msg) {
        var toast = document.getElementById("toast");
        if (!toast) return;
        toast.textContent = msg;
        toast.style.opacity = "1";
        setTimeout(function() { toast.style.opacity = "0"; }, 2500);
    },

    _esc: function(str) {
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    },
};
