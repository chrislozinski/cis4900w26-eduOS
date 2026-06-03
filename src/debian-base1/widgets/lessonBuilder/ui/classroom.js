"use strict";

var ClassroomScreen = {
    _filter:    "all",
    _classroom: null,
    _trashItems: [],

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

        var tabs = document.getElementById("classroom-tabs");
        tabs.innerHTML = [
            '<button class="filter-tab active" data-tab="all" onclick="ClassroomScreen._setFilter(this,\'all\')">All</button>',
            '<button class="filter-tab" data-tab="published" onclick="ClassroomScreen._setFilter(this,\'published\')">Published</button>',
            '<button class="filter-tab" data-tab="drafts" onclick="ClassroomScreen._setFilter(this,\'drafts\')">Drafts</button>',
            '<button class="filter-tab" data-tab="bin" onclick="ClassroomScreen._setFilter(this,\'bin\')">Recycle Bin</button>',
        ].join("");

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
                        '<div class="lesson-list-row">',
                        '<div class="lesson-list-name">' + ClassroomScreen._esc(item.title || "Untitled") + "</div>",
                        '<button class="btn btn-secondary btn-sm" onclick="ClassroomScreen._recover(' + JSON.stringify(id) + ')">Recover</button>',
                        '<button class="btn btn-danger btn-sm" onclick="ClassroomScreen._permDelete(' + JSON.stringify(id) + ')">Delete</button>',
                        "</div>",
                    ].join("");
                }).join("");
            }
            return;
        }

        var enabledIds = cls.enabled_lessons || [];
        var drafts     = State.drafts;
        var items      = [];

        if (this._filter === "all") {
            items = drafts;
        } else if (this._filter === "published") {
            items = drafts.filter(function(d) { return enabledIds.indexOf(d.id) !== -1; });
        } else if (this._filter === "drafts") {
            items = drafts.filter(function(d) { return enabledIds.indexOf(d.id) === -1; });
        }

        if (items.length === 0) {
            list.innerHTML = '<div class="no-lessons">No lessons here yet.</div>';
            return;
        }

        list.innerHTML = items.map(function(lesson) {
            var id         = lesson.id || "";
            var isPublished = enabledIds.indexOf(id) !== -1;
            var status     = isPublished ? "published" : "draft";
            return [
                '<div class="lesson-list-row">',
                '<div class="lesson-list-name">' + ClassroomScreen._esc(lesson.title || "Untitled") + "</div>",
                '<span class="lesson-list-status ' + status + '">' + status + "</span>",
                '<button class="btn btn-secondary btn-sm" onclick="ClassroomScreen._openLesson(' + JSON.stringify(id) + ')">Open</button>',
                "</div>",
            ].join("");
        }).join("");
    },

    _openLesson: function(lessonId) {
        State.activeLesson = State.drafts.find(function(d) { return d.id === lessonId; }) || { id: lessonId };
        sendToPython("loadDraft", { lessonId: lessonId });
        navigate("editor", { lessonId: lessonId });
    },

    _recover: function(lessonId) {
        sendToPython("recoverLesson", { lessonId: lessonId });
    },

    _permDelete: function(lessonId) {
        if (!confirm("Permanently delete this lesson? This cannot be undone.")) return;
        sendToPython("permanentDelete", { lessonId: lessonId });
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
