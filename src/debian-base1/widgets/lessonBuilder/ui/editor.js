"use strict";

var EditorScreen = {
    _draft:      null,
    _lessonId:   null,
    _stepIdx:    0,
    _collapsed:  {},

    onEnter: function(data) {
        if (data && data.lessonId && data.lessonId !== this._lessonId) {
            this._lessonId = data.lessonId;
            this._stepIdx  = 0;
            sendToPython("loadDraft", { lessonId: data.lessonId });
        } else if (this._draft) {
            this._render();
        }
    },

    onDraftLoaded: function(lessonId, draft) {
        this._lessonId = lessonId;
        this._draft    = draft || { id: lessonId, title: "", steps: [], solution_code: "" };
        this._stepIdx  = Math.min(this._stepIdx, Math.max(0, (this._draft.steps || []).length - 1));
        sendToPython("setCurrentLesson", { lessonId: lessonId, stepIndex: this._stepIdx });
        var firstStep = (this._draft.steps || [])[this._stepIdx];
        sendToPython("setEditorCode", { code: firstStep ? (firstStep.captured_code || "") : "" });
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
        el.innerHTML = State.drafts.map(function(d) {
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
        if (!el || !this._draft) return;
        var steps   = this._draft.steps || [];
        var current = this._stepIdx;
        el.innerHTML = steps.map(function(step, i) {
            var active = i === current ? " active" : "";
            return [
                '<div class="step-item' + active + '" onclick="EditorScreen._selectStep(' + i + ')">',
                '<div class="step-number">' + (i + 1) + "</div>",
                '<div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + EditorScreen._esc(step.title || "Step " + (i + 1)) + "</div>",
                "</div>",
            ].join("");
        }).join("");
    },

    _renderStepFields: function() {
        var draft = this._draft;
        if (!draft) return;
        var steps = draft.steps || [];
        var step  = steps[this._stepIdx] || null;

        var titleEl        = document.getElementById("step-title");
        var instructionsEl = document.getElementById("step-instructions");
        var hintEl         = document.getElementById("step-hint");
        var codePreviewEl  = document.getElementById("step-code-preview");

        if (titleEl)        titleEl.value        = step ? (step.title        || "") : "";
        if (instructionsEl) instructionsEl.value = step ? (step.instructions || "") : "";
        if (hintEl)         hintEl.value         = step ? (step.hint         || "") : "";
        if (codePreviewEl)  codePreviewEl.textContent = step ? (step.captured_code || "(auto-saved as you type)") : "";

        var noStepMsg = document.getElementById("no-step-msg");
        var stepEditor = document.getElementById("step-editor-fields");
        if (noStepMsg)  noStepMsg.style.display  = steps.length === 0 ? "" : "none";
        if (stepEditor) stepEditor.style.display = steps.length === 0 ? "none" : "";
    },

    _selectStep: function(idx) {
        this._flushCurrentStepFields();
        this._stepIdx = idx;
        sendToPython("setCurrentStep", { stepIndex: idx });
        this._renderStepList();
        this._renderStepFields();
        var step = (this._draft.steps || [])[idx];
        sendToPython("setEditorCode", { code: step ? (step.captured_code || "") : "" });
    },

    _addStep: function() {
        if (!this._draft) return;
        var steps    = this._draft.steps || [];
        var prevCode = steps.length > 0 ? (steps[steps.length - 1].captured_code || "") : "";
        steps.push({ title: "", instructions: "", hint: "", captured_code: prevCode });
        this._draft.steps = steps;
        this._saveDraft();
        this._stepIdx = steps.length - 1;
        sendToPython("setCurrentStep", { stepIndex: this._stepIdx });
        this._render();
        sendToPython("setEditorCode", { code: prevCode });
    },

    _deleteStep: function(idx) {
        if (!this._draft) return;
        var steps = this._draft.steps || [];
        if (steps.length === 0) return;
        steps.splice(idx, 1);
        this._draft.steps = steps;
        this._stepIdx     = Math.min(this._stepIdx, Math.max(0, steps.length - 1));
        sendToPython("setCurrentStep", { stepIndex: this._stepIdx });
        this._saveDraft();
        this._render();
    },

    _moveStep: function(idx, direction) {
        var steps  = this._draft.steps || [];
        var target = idx + direction;
        if (target < 0 || target >= steps.length) return;
        var tmp       = steps[idx];
        steps[idx]    = steps[target];
        steps[target] = tmp;
        this._draft.steps = steps;
        this._stepIdx     = target;
        sendToPython("setCurrentStep", { stepIndex: target });
        this._saveDraft();
        this._render();
    },

    _switchLesson: function(lessonId) {
        if (lessonId === this._lessonId) return;
        this._flushCurrentStepFields();
        this._saveDraft();
        this._stepIdx  = 0;
        this._lessonId = lessonId;
        sendToPython("loadDraft", { lessonId: lessonId });
    },

    _flushCurrentStepFields: function() {
        if (!this._draft) return;
        var steps = this._draft.steps || [];
        var step  = steps[this._stepIdx];
        if (!step) return;
        var titleEl        = document.getElementById("step-title");
        var instructionsEl = document.getElementById("step-instructions");
        var hintEl         = document.getElementById("step-hint");
        if (titleEl)        step.title        = titleEl.value;
        if (instructionsEl) step.instructions = instructionsEl.value;
        if (hintEl)         step.hint         = hintEl.value;
    },

    _saveDraft: function() {
        if (!this._draft || !this._lessonId) return;
        this._flushCurrentStepFields();
        sendToPython("saveDraft", { lessonId: this._lessonId, draft: this._draft });
    },

    _publishDialog: function() {
        if (!this._lessonId || !this._draft) return;
        var classroom = State.activeClassroom || State.classrooms[0];
        if (!classroom) {
            ConfirmDialog.show("No classrooms available.", "OK", "btn-secondary", null);
            return;
        }
        var self = this;
        ConfirmDialog.show(
            'Publish "' + this._esc(this._draft.title || "this lesson") + '" to ' + this._esc(classroom.name || classroom.id) + "?",
            "Publish", "btn-success",
            function(ok) {
                if (!ok) return;
                self._flushCurrentStepFields();
                var steps = self._draft.steps || [];
                if (steps.length > 0)
                    self._draft.solution_code = steps[steps.length - 1].captured_code || "";
                sendToPython("publishLesson", {
                    lessonId:    self._lessonId,
                    classroomId: classroom.id,
                    draft:       self._draft,
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
        if (!this._draft) { navigate("classroom", { classroomId: State.activeClassroom && State.activeClassroom.id }); return; }
        document.getElementById("dialog-save-back").classList.remove("hidden");
    },

    _confirmBack: function(save) {
        document.getElementById("dialog-save-back").classList.add("hidden");
        if (save) this._saveDraft();
        navigate("classroom", { classroomId: State.activeClassroom && State.activeClassroom.id });
    },

    _previewLesson: function() {
        if (!this._lessonId || !this._draft) return;
        this._flushCurrentStepFields();
        sendToPython("previewLesson", { lessonId: this._lessonId, draft: this._draft });
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
