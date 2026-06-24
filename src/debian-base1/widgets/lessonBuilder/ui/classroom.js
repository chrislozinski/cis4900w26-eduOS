"use strict";

var ClassroomScreen = {
    _filter:    "all",
    _classroom: null,
    _trashItems: [],
    _activeCardId: null,

    onEnter: function(data) {
        if (data && data.classroomId) {
            this._classroom = State.classrooms.find(function(c) { return c.id === data.classroomId; }) || null;
        }
        this._filter = "all";
        this._render();
    },

    refresh: function() {
        this._render();
    },

    onTrashLoaded: function(items) {
        this._trashItems = items;
        this._renderList();
    },

    _render: function() {
        if (!this._classroom) return;
        var cls  = this._classroom;
        var name = cls.name || cls.id;

        document.getElementById("classroom-name").textContent = name;
        State.activeClassroom = cls;

        var activeFilter = this._filter;
        var tabData = [
            { id: "all",       label: "All" },
            { id: "published", label: "Published" },
            { id: "drafts",    label: "Drafts" },
            { id: "bin",       label: "Recycle Bin" },
        ];
        var tabs = document.getElementById("classroom-tabs");
        tabs.innerHTML = tabData.map(function(tab) {
            return '<button class="filter-tab' + (activeFilter === tab.id ? " active" : "") +
                   '" data-tab="' + tab.id + '" onclick="ClassroomScreen._setFilter(this,\'' + tab.id + '\')">' + tab.label + '</button>';
        }).join("");

        this._renderList();
    },

    _setFilter: function(btnEl, filter) {
        document.querySelectorAll("#classroom-tabs .filter-tab").forEach(function(b) {
            b.classList.remove("active");
        });
        btnEl.classList.add("active");
        this._filter = filter;
        if (filter === "bin") {
            sendToPython("getTrash", {});
        }
        this._renderList();
    },

    _renderList: function() {
        var list = document.getElementById("classroom-lesson-list");
        if (!list || !this._classroom) return;

        var cls = this._classroom;

        if (this._filter === "bin") {
            if (!this._trashItems || this._trashItems.length === 0) {
                list.innerHTML = '<div class="no-lessons">Recycle bin is empty.</div>';
            } else {
                list.innerHTML = this._trashItems.map(function(item) {
                    var id = item.id || "";
                    return [
                        '<div class="lesson-bin-card">',
                        '<div class="lesson-bin-name">' + ClassroomScreen._esc(item.title || "Untitled") + "</div>",
                        '<div class="lesson-bin-actions">',
                        '<button class="btn btn-secondary btn-sm" onclick="ClassroomScreen._recover(' + _attr(id) + ')">Recover</button>',
                        '<button class="btn btn-danger btn-sm" onclick="ClassroomScreen._confirmPermDelete(' + _attr(id) + ')">Delete Permanently</button>',
                        "</div>",
                        "</div>",
                    ].join("");
                }).join("");
            }
            return;
        }

        var enabledIds = cls.enabled_lessons || [];
        var lessons    = State.lessons;
        var items      = [];

        if (this._filter === "all") {
            items = lessons.filter(function(d) {
                return enabledIds.indexOf(d.id) !== -1 || d.classroom_id === cls.id;
            });
        } else if (this._filter === "published") {
            items = lessons.filter(function(d) { return enabledIds.indexOf(d.id) !== -1; });
        } else if (this._filter === "drafts") {
            items = lessons.filter(function(d) {
                return d.classroom_id === cls.id && enabledIds.indexOf(d.id) === -1;
            });
        }

        if (items.length === 0) {
            list.innerHTML = '<div class="no-lessons">No lessons here yet.</div>';
            return;
        }

        list.innerHTML = items.map(function(lesson) {
            var id          = lesson.id || "";
            var isPublished = enabledIds.indexOf(id) !== -1;
            var status      = isPublished ? "published" : "draft";
            return [
                '<div class="lesson-list-row">',
                '<div class="lesson-card-head">',
                '<div class="lesson-list-name">' + ClassroomScreen._esc(lesson.title || "Untitled"),
                ' <span class="rename-pencil" onclick="ClassroomScreen._renameLesson(' + _attr(id) + ')">✎</span>',
                '</div>',
                '<span class="lesson-list-status ' + status + '">' + status + '</span>',
                '</div>',
                '<div class="lesson-card-actions">',
                '<button class="btn btn-primary btn-sm" onclick="ClassroomScreen._openLesson(' + _attr(id) + ')">Open</button>',
                '<button class="btn btn-danger btn-sm" onclick="ClassroomScreen._trashLesson(' + _attr(id) + ')">→ Bin</button>',
                '</div>',
                '</div>',
            ].join("");
        }).join("");
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

    _recover: function(lessonId) {
        sendToPython("recoverLesson", { lessonId: lessonId });
    },

    _confirmPermDelete: function(lessonId) {
        ConfirmDialog.show("Permanently delete this lesson? This cannot be undone.", "Delete Forever", "btn-danger", function(ok) {
            if (ok) sendToPython("permanentDelete", { lessonId: lessonId });
        });
    },

    _renameLesson: function(lessonId) {
        var lesson = State.lessons.find(function(d) { return d.id === lessonId; });
        if (!lesson) return;
        var newTitle = prompt("Rename lesson:", lesson.title || "");
        if (newTitle === null || newTitle.trim() === "") return;
        sendToPython("renameLesson", { lessonId: lessonId, title: newTitle.trim() });
    },

    _esc: function(str) {
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    },
};


// New Lesson dialog
var NewLessonDialog = {
    _classroomId: null,

    show: function(classroomId) {
        this._classroomId = classroomId;
        document.getElementById("new-lesson-title").value       = "";
        document.getElementById("new-lesson-description").value = "";
        document.getElementById("dialog-new-lesson").classList.remove("hidden");
        document.getElementById("new-lesson-title").focus();
    },

    hide: function() {
        document.getElementById("dialog-new-lesson").classList.add("hidden");
    },

    confirm: function() {
        var title = document.getElementById("new-lesson-title").value.trim();
        if (!title) {
            document.getElementById("new-lesson-title").focus();
            return;
        }
        var desc = document.getElementById("new-lesson-description").value.trim();
        this.hide();
        sendToPython("createLesson", {
            title:       title,
            description: desc,
            classroomId: this._classroomId,
        });
    },
};
