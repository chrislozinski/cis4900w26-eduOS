"use strict";

var HomeScreen = {
    onEnter: function(data) {
        this._render();
    },

    _render: function() {
        var content = document.getElementById("home-content");
        if (!content) return;

        if (State.classrooms.length === 0) {
            content.innerHTML = '<p style="color:#555;text-align:center;padding:40px 0;">No classrooms found. Add classrooms in Classroom Manager.</p>';
            return;
        }

        var html = "";
        State.classrooms.forEach(function(cls) {
            var lessons = HomeScreen._lessonsForClassroom(cls);
            var lessonRows = "";

            var visible = lessons.slice(0, 3);
            var enabledIds = cls.enabled_lessons || [];
            visible.forEach(function(lesson) {
                var isPublished = enabledIds.indexOf(lesson.id) !== -1;
                var dotClass    = isPublished ? "published" : "draft";
                var statusText  = isPublished ? "published" : "draft";
                lessonRows += [
                    '<div class="lesson-row">',
                    '<div class="lesson-dot ' + dotClass + '"></div>',
                    '<div class="lesson-name">' + HomeScreen._esc(lesson.title || "Untitled") + "</div>",
                    '<span style="font-size:11px;color:#' + (isPublished ? "3d9970" : "666") + '">' + statusText + "</span>",
                    "</div>",
                ].join("");
            });

            if (lessons.length > 3) {
                lessonRows += '<div class="more-label">' + (lessons.length - 3) + " more…</div>";
            }

            if (!lessonRows) {
                lessonRows = '<div class="empty-classroom">No lessons yet</div>';
            }

            html += [
                '<div class="classroom-card" onclick="HomeScreen._openClassroom(' + _attr(cls.id) + ')">',
                '<div class="classroom-header">',
                '<div class="classroom-name">' + HomeScreen._esc(cls.name || cls.id) + "</div>",
                '<div class="classroom-chevron">›</div>',
                "</div>",
                '<div class="classroom-lessons">' + lessonRows + "</div>",
                "</div>",
            ].join("");
        });

        content.innerHTML = html;
    },

    _lessonsForClassroom: function(cls) {
        var enabledIds = cls.enabled_lessons || [];
        var result     = [];

        enabledIds.forEach(function(id) {
            var d = State.lessons.find(function(x) { return x.id === id; });
            if (d) result.push(d);
        });

        State.lessons.forEach(function(d) {
            if (enabledIds.indexOf(d.id) === -1 && d.classroom_id === cls.id) result.push(d);
        });

        return result;
    },

    _openClassroom: function(classroomId) {
        navigate("classroom", { classroomId: classroomId });
    },

    _esc: function(str) {
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    },
};
