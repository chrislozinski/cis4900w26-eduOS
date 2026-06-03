"use strict";

// State shared across screens
var State = {
    classrooms:       [],
    drafts:           [],
    activeClassroom:  null,
    activeLesson:     null,
    draft:            null,
};

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
        State.drafts     = payload.drafts     || [];
        navigate("home", {});
        return;
    }

    if (action === "classroomsUpdated") {
        State.classrooms = payload.classrooms || [];
        if (document.getElementById("screen-home").classList.contains("active")) {
            HomeScreen._render();
        }
        return;
    }

    if (action === "lessonCreated") {
        State.drafts.push({ id: payload.lessonId, title: payload.draft.title, lesson_type: payload.draft.lesson_type, published_to: [] });
        EditorScreen.onDraftLoaded(payload.lessonId, payload.draft);
        navigate("editor", { lessonId: payload.lessonId });
        return;
    }

    if (action === "draftLoaded") {
        EditorScreen.onDraftLoaded(payload.lessonId, payload.draft);
        return;
    }

    if (action === "draftSaved") {
        // no UI update needed
        return;
    }

    if (action === "lessonPublished") {
        var classroom = payload.classroomId;
        State.drafts.forEach(function(d) {
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
        State.drafts = State.drafts.filter(function(d) { return d.id !== payload.lessonId; });
        if (State.activeClassroom) {
            navigate("classroom", { classroomId: State.activeClassroom.id });
        } else {
            navigate("home", {});
        }
        return;
    }

    if (action === "lessonRecovered") {
        State.drafts.push({ id: payload.lessonId, title: (payload.draft || {}).title || "", published_to: [] });
        ClassroomScreen.refresh();
        return;
    }

    if (action === "lessonPermanentlyDeleted") {
        ClassroomScreen.refresh();
        return;
    }

    if (action === "trashLoaded") {
        ClassroomScreen.onTrashLoaded(payload.items || []);
        return;
    }

    if (action === "previewReady") {
        // Preview window opened by Python — nothing to update in the UI
        return;
    }

    if (action === "error") {
        console.error("Python error [" + payload.source + "]:", payload.error);
        return;
    }
};

// Request initial data when the page loads
window.addEventListener("load", function() {
    sendToPython("init", {});
});
