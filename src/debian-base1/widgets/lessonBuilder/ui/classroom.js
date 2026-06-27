"use strict";

var ClassroomScreen = {
    _classroom: null,

    onEnter: function(data) {
        if (data && data.classroomId) {
            this._classroom = State.classrooms.find(function(c) { return c.id === data.classroomId; }) || null;
        }
        this._render();
    },

    refresh: function() {
        this._render();
    },

    _render: function() {
        if (!this._classroom) return;
        var cls = this._classroom;
        document.getElementById("classroom-name").textContent = cls.name || cls.id;
        State.activeClassroom = cls;
        this._renderList();
    },

    _renderList: function() {
        var list = document.getElementById("classroom-lesson-list");
        if (!list || !this._classroom) return;
        var cls        = this._classroom;
        var enabledIds = cls.enabled_lessons || [];
        var all        = State.lessons.filter(function(d) {
            return enabledIds.indexOf(d.id) !== -1 || d.classroom_id === cls.id;
        });
        var lessonRows = "";
        all.forEach(function(lesson) {
            var pub = enabledIds.indexOf(lesson.id) !== -1;
            lessonRows +=
                '<div class="lesson-row">' +
                '<div class="lesson-dot ' + (pub ? "published" : "draft") + '"></div>' +
                '<div class="lesson-name">' + ClassroomScreen._esc(lesson.title || "Untitled") + '</div>' +
                '<span class="lesson-list-status ' + (pub ? "published" : "draft") + '">' + (pub ? "Published" : "Draft") + '</span>' +
                '</div>';
        });
        var lessonsSection = all.length
            ? '<div class="classroom-lessons">' + lessonRows + '</div>'
            : '<div class="classroom-lessons"><p class="empty-classroom">No lessons yet.</p></div>';
        list.innerHTML =
            '<div class="classroom-card" onclick="navigate(\'lessons\',{classroomId:' + _attr(cls.id) + '})">' +
            '<div class="classroom-header">' +
            '<span class="classroom-name">Coding Lessons</span>' +
            '<span class="classroom-arrow">Open &#8250;</span>' +
            '</div>' +
            lessonsSection +
            '</div>';
    },

    _esc: function(str) {
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    },
};


var UnitLessonScreen = {
    _filter:     "all",
    _trashItems: [],

    onEnter: function(data) {
        this._filter = "all";
        this._render();
    },

    refresh: function() { this._render(); },

    onTrashLoaded: function(items) {
        this._trashItems = items;
        this._renderList();
    },

    _render: function() {
        if (!document.getElementById("screen-lessons").classList.contains("active")) return;
        var cls = State.activeClassroom;
        if (!cls) return;
        var enabledIds = cls.enabled_lessons || [];
        var total      = State.lessons.filter(function(d) {
            return enabledIds.indexOf(d.id) !== -1 || d.classroom_id === cls.id;
        }).length;

        var backBtn = document.getElementById("lessons-back-btn");
        if (backBtn) backBtn.textContent = "< All Units";
        var crumb = document.getElementById("lessons-crumb");
        if (crumb) crumb.textContent = "Coding Lessons";
        var meta = document.getElementById("lessons-meta");
        if (meta) meta.textContent = total + " lesson" + (total !== 1 ? "s" : "") + " \xb7 ID: " + cls.id;

        var af      = this._filter;
        var tabs    = document.getElementById("lessons-tabs");
        var tabData = [
            { id: "all",       label: "All" },
            { id: "published", label: "Published" },
            { id: "drafts",    label: "Drafts" },
            { id: "bin",       label: "Recycle Bin" },
        ];
        if (tabs) {
            var tabHtml = "";
            tabData.forEach(function(t) {
                tabHtml += '<button class="filter-tab' + (af === t.id ? " active" : "") +
                    '" onclick="UnitLessonScreen._setFilter(this,\'' + t.id + '\')">' + t.label + '</button>';
            });
            tabs.innerHTML = tabHtml;
        }
        this._renderList();
    },

    _setFilter: function(btnEl, filter) {
        document.querySelectorAll("#lessons-tabs .filter-tab").forEach(function(b) { b.classList.remove("active"); });
        btnEl.classList.add("active");
        this._filter = filter;
        if (filter === "bin") sendToPython("getTrash", {});
        this._renderList();
    },

    _filteredLessons: function(cls) {
        var enabledIds = cls.enabled_lessons || [];
        if (this._filter === "all")
            return State.lessons.filter(function(d) { return enabledIds.indexOf(d.id) !== -1 || d.classroom_id === cls.id; });
        if (this._filter === "published")
            return State.lessons.filter(function(d) { return enabledIds.indexOf(d.id) !== -1; });
        if (this._filter === "drafts")
            return State.lessons.filter(function(d) { return d.classroom_id === cls.id && enabledIds.indexOf(d.id) === -1; });
        return [];
    },

    _lessonRow: function(lesson, enabledIds) {
        var id  = lesson.id || "";
        var pub = enabledIds.indexOf(id) !== -1;
        var sc  = pub ? "published" : "draft";
        return '<div class="lesson-row-item" ondblclick="event.stopPropagation();UnitLessonScreen._openLesson(' + _attr(id) + ')">' +
            '<div class="lesson-row-head">' +
            '<div class="lesson-row-title">' + ClassroomScreen._esc(lesson.title || "Untitled") + '</div>' +
            '<span class="lesson-type-chip mc">MakeCode</span>' +
            '<span class="lesson-status-chip ' + sc + '">' + (pub ? "Published" : "Draft") + '</span>' +
            '</div>' +
            '<div class="lesson-row-actions">' +
            '<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();UnitLessonScreen._openLesson(' + _attr(id) + ')">Open Editor</button>' +
            '<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();UnitLessonScreen._renameLesson(' + _attr(id) + ')">Rename</button>' +
            '<button class="btn btn-danger btn-sm" style="margin-left:auto" onclick="event.stopPropagation();UnitLessonScreen._trashLesson(' + _attr(id) + ')">Move to Bin</button>' +
            '</div></div>';
    },

    _binRow: function(item) {
        var id = item.id || "";
        return '<div class="bin-row-item">' +
            '<div class="bin-row-title">' + ClassroomScreen._esc(item.title || "Untitled") + '</div>' +
            '<div class="bin-row-actions">' +
            '<button class="btn btn-secondary btn-sm" onclick="UnitLessonScreen._recover(' + _attr(id) + ')">Recover</button>' +
            '<button class="btn btn-danger btn-sm" onclick="UnitLessonScreen._confirmPermDelete(' + _attr(id) + ')">Delete</button>' +
            '</div></div>';
    },

    _renderList: function() {
        if (!document.getElementById("screen-lessons").classList.contains("active")) return;
        var list = document.getElementById("lessons-list");
        if (!list || !State.activeClassroom) return;
        var cls = State.activeClassroom;

        if (this._filter === "bin") {
            list.innerHTML = this._trashItems.length
                ? '<div class="lesson-list-flat">' + this._trashItems.map(this._binRow).join("") + '</div>'
                : '<div class="no-lessons">Recycle bin is empty.</div>';
            return;
        }

        var enabledIds = cls.enabled_lessons || [];
        var items      = this._filteredLessons(cls);
        if (!items.length) {
            list.innerHTML = '<div class="no-lessons">No lessons here yet.</div>';
            return;
        }
        var rows = "";
        items.forEach(function(l) { rows += UnitLessonScreen._lessonRow(l, enabledIds); });
        list.innerHTML = '<div class="lesson-list-flat">' + rows + '</div>';
    },

    _openLesson: function(lessonId) {
        State.activeLesson = State.lessons.find(function(d) { return d.id === lessonId; }) || { id: lessonId };
        sendToPython("loadLesson", { lessonId: lessonId });
        navigate("editor", { lessonId: lessonId });
    },

    _trashLesson: function(lessonId) {
        ConfirmDialog.show("Move this lesson to the recycle bin?", "Move to Bin", "btn-danger", function(ok) {
            if (ok) sendToPython("deleteLesson", { lessonId: lessonId });
        });
    },

    _recover: function(lessonId) { sendToPython("recoverLesson", { lessonId: lessonId }); },

    _confirmPermDelete: function(lessonId) {
        ConfirmDialog.show("Permanently delete this lesson? This cannot be undone.", "Delete Forever", "btn-danger", function(ok) {
            if (ok) sendToPython("permanentDelete", { lessonId: lessonId });
        });
    },

    _renameLesson: function(lessonId) {
        var lesson = State.lessons.find(function(d) { return d.id === lessonId; });
        if (!lesson) return;
        RenameDialog.show(lessonId, lesson.title || "");
    },
};


var NewLessonDialog = {
    _classroomId: null,

    show: function(classroomId) {
        this._classroomId = classroomId;
        document.getElementById("new-lesson-title").value       = "";
        document.getElementById("new-lesson-description").value = "";
        document.getElementById("dialog-create-step1").classList.remove("hidden");
        document.getElementById("dialog-create-step2").classList.add("hidden");
    },

    hide: function() {
        document.getElementById("dialog-create-step1").classList.add("hidden");
        document.getElementById("dialog-create-step2").classList.add("hidden");
    },

    _pickType: function(type) {
        if (type !== "makecode") return;
        document.getElementById("dialog-create-step1").classList.add("hidden");
        document.getElementById("dialog-create-step2").classList.remove("hidden");
        setTimeout(function() { var t = document.getElementById("new-lesson-title"); if (t) t.focus(); }, 50);
    },

    _backToStep1: function() {
        document.getElementById("dialog-create-step2").classList.add("hidden");
        document.getElementById("dialog-create-step1").classList.remove("hidden");
    },

    confirm: function() {
        var title = (document.getElementById("new-lesson-title").value || "").trim();
        if (!title) { document.getElementById("new-lesson-title").focus(); return; }
        var desc = document.getElementById("new-lesson-description").value || "";
        this.hide();
        sendToPython("createLesson", { classroomId: this._classroomId, title: title, description: desc });
    },
};
