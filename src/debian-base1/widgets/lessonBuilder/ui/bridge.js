"use strict";

// Reusable dark-theme confirmation dialog
var ConfirmDialog = {
    _cb: null,
    show: function(title, okLabel, okClass, cb) {
        this._cb = cb;
        document.getElementById("dialog-confirm-title").textContent = title;
        var ok = document.getElementById("dialog-confirm-ok");
        ok.textContent = okLabel || "OK";
        ok.className = "btn " + (okClass || "btn-primary");
        document.getElementById("dialog-confirm").classList.remove("hidden");
    },
    _ok: function() {
        document.getElementById("dialog-confirm").classList.add("hidden");
        if (this._cb) this._cb(true);
    },
    _cancel: function() {
        document.getElementById("dialog-confirm").classList.add("hidden");
        if (this._cb) this._cb(false);
    },
};

// State shared across screens
var State = {
    classrooms:       [],
    lessons:          [],
    activeClassroom:  null,
    activeLesson:     null,
    lesson:           null,
};

// JSON-stringify a value for use inside an HTML double-quoted attribute.
// JSON.stringify produces surrounding " chars that would break the attribute.
function _attr(val) {
    return JSON.stringify(val).replace(/"/g, '&quot;');
}

// Send an action to Python
function sendToPython(action, data) {
    window.webkit.messageHandlers.lessonAction.postMessage(
        JSON.stringify({ action: action, data: data || {} })
    );
}

// Navigate between screens
function navigate(screen, data) {
    document.querySelectorAll(".screen").forEach(function(s) {
        s.classList.remove("active");
    });
    var el = document.getElementById("screen-" + screen);
    if (el) {
        el.classList.add("active");
    }
    if (screen === "editor") {
        sendToPython("showEditor", {});
        EditorScreen.onEnter(data);
    } else {
        sendToPython("hideEditor", {});
        if (screen === "home") {
            HomeScreen.onEnter(data);
        } else if (screen === "classroom") {
            ClassroomScreen.onEnter(data);
        }
    }
}

// Dispatch Python responses to the active screen handler
window.receiveFromPython = function(payload) {
    var action = payload.action;

    if (action === "initData") {
        State.classrooms = payload.classrooms || [];
        State.lessons    = payload.lessons    || [];
        navigate("home", {});
        return;
    }

    if (action === "classroomsUpdated") {
        State.classrooms = payload.classrooms || [];
        if (ClassroomScreen._classroom) {
            ClassroomScreen._classroom = State.classrooms.find(function(c) {
                return c.id === ClassroomScreen._classroom.id;
            }) || ClassroomScreen._classroom;
        }
        if (State.activeClassroom) {
            State.activeClassroom = State.classrooms.find(function(c) {
                return c.id === State.activeClassroom.id;
            }) || State.activeClassroom;
        }
        if (document.getElementById("screen-home").classList.contains("active")) {
            HomeScreen._render();
        } else if (document.getElementById("screen-classroom").classList.contains("active")) {
            ClassroomScreen.refresh();
        }
        return;
    }

    if (action === "lessonCreated") {
        State.lessons.push({ id: payload.lessonId, title: payload.lesson.title, lesson_type: payload.lesson.lesson_type, published_to: [], classroom_id: payload.lesson.classroom_id || "" });
        EditorScreen.onLessonLoaded(payload.lessonId, payload.lesson);
        navigate("editor", { lessonId: payload.lessonId });
        return;
    }

    if (action === "lessonLoaded") {
        EditorScreen.onLessonLoaded(payload.lessonId, payload.lesson);
        return;
    }

    if (action === "lessonSaved") {
        EditorScreen._showToast("Saved.");
        return;
    }

    if (action === "lessonPublished") {
        var classroom = payload.classroomId;
        State.lessons.forEach(function(d) {
            if (d.id === payload.lessonId) {
                if (!d.published_to) d.published_to = [];
                if (d.published_to.indexOf(classroom) === -1) {
                    d.published_to.push(classroom);
                }
            }
        });
        State.classrooms.forEach(function(cls) {
            if (cls.id === classroom) {
                if (!cls.enabled_lessons) cls.enabled_lessons = [];
                if (cls.enabled_lessons.indexOf(payload.lessonId) === -1) {
                    cls.enabled_lessons.push(payload.lessonId);
                }
            }
        });
        EditorScreen.onPublished(payload.lessonId, payload.classroomId);
        return;
    }

    if (action === "lessonUnpublished") {
        State.classrooms.forEach(function(cls) {
            if (cls.id === payload.classroomId) {
                cls.enabled_lessons = (cls.enabled_lessons || []).filter(function(id) {
                    return id !== payload.lessonId;
                });
            }
        });
        return;
    }

    if (action === "lessonDeleted") {
        State.lessons = State.lessons.filter(function(d) { return d.id !== payload.lessonId; });
        if (State.activeClassroom) {
            navigate("classroom", { classroomId: State.activeClassroom.id });
        } else {
            navigate("home", {});
        }
        return;
    }

    if (action === "lessonRecovered") {
        State.lessons.push({ id: payload.lessonId, title: (payload.lesson || {}).title || "", published_to: [], classroom_id: (payload.lesson || {}).classroom_id || "" });
        ClassroomScreen._filter = "all";
        ClassroomScreen._render();
        return;
    }

    if (action === "lessonRenamed") {
        State.lessons.forEach(function(d) { if (d.id === payload.lessonId) d.title = payload.title; });
        ClassroomScreen.refresh();
        return;
    }

    if (action === "lessonPermanentlyDeleted") {
        ClassroomScreen._trashItems = ClassroomScreen._trashItems.filter(function(i) {
            return i.id !== payload.lessonId;
        });
        ClassroomScreen._renderList();
        return;
    }

    if (action === "trashLoaded") {
        ClassroomScreen.onTrashLoaded(payload.items || []);
        return;
    }

    if (action === "stepCodeUpdated") {
        if (EditorScreen._lesson && EditorScreen._lesson.steps) {
            var step = EditorScreen._lesson.steps.find(function(s) {
                return s.id === payload.stepId;
            });
            if (step) {
                step.raw_ts     = payload.rawTs;
                step.cached_xml = payload.cachedXml;
            }
        }
        return;
    }

    if (action === "previewReady") {
        return;
    }

    if (action === "error") {
        console.error("Python error [" + payload.source + "]:", payload.error);
        EditorScreen._showToast("Error (" + (payload.source || "?") + "): " + payload.error);
        return;
    }
};

// Request initial data when the page loads
window.addEventListener("load", function() {
    sendToPython("init", {});
});
