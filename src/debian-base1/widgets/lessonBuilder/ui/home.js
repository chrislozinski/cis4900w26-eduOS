"use strict";

var CARD_ACCENTS = ['#4A6741','#4A7A8A','#7A4A6A','#8A6A4A','#4A4A8A','#7A4A4A'];

var SettingsMenu = {
    toggle: function(btn) {
        var target = btn.nextElementSibling;
        var isHidden = target.classList.contains("hidden");
        document.querySelectorAll(".settings-pop").forEach(function(p) { p.classList.add("hidden"); });
        if (isHidden) target.classList.remove("hidden");
    },
    close: function() {
        document.querySelectorAll(".settings-pop").forEach(function(p) { p.classList.add("hidden"); });
    },
};

var HomeScreen = {
    _lastSig: "",

    onEnter: function(data) {
        this._render();
    },

    _render: function() {
        var content = document.getElementById("home-content");
        if (!content) return;
        var sig = State.classrooms.map(function(c) {
            var count = State.lessons.filter(function(d) {
                return (c.enabled_lessons || []).indexOf(d.id) !== -1 || d.classroom_id === c.id;
            }).length;
            return c.id + ":" + (c.enabled_lessons || []).join("|") + ":" + count;
        }).join(",");
        if (this._lastSig === sig && content.children.length) return;
        this._lastSig = sig;
        if (!State.classrooms.length) {
            content.innerHTML = '<p style="color:var(--ink3);text-align:center;padding:60px 0;">No classrooms found. Add classrooms in Classroom Manager.</p>';
            return;
        }
        var html = "";
        State.classrooms.forEach(function(cls, i) {
            var accent;
            try { accent = localStorage.getItem('lb-cls-color-' + cls.id) || CARD_ACCENTS[i % CARD_ACCENTS.length]; }
            catch(e) { accent = CARD_ACCENTS[i % CARD_ACCENTS.length]; }
            var lessons    = HomeScreen._lessonsForClassroom(cls);
            var enabledIds = cls.enabled_lessons || [];
            var pubCount   = lessons.filter(function(l) { return enabledIds.indexOf(l.id) !== -1; }).length;
            var stats      = pubCount + " published · " + (lessons.length - pubCount) + " drafts";
            html += HomeScreen._cardHtml(cls, accent, stats);
        });
        /* html += '<div class="class-card-new" onclick="HomeScreen._showNewClassInfo()">+ New Class</div>'; */
        content.innerHTML = '<div class="class-grid">' + html + '</div>';
    },

    _cardHtml: function(cls, accent, stats) {
        var id = cls.id;
        return '<div class="class-card" onclick="HomeScreen._openClassroom(' + _attr(id) + ')">' +
            '<div class="class-card-stripe" id="stripe-' + id + '" style="background:' + accent + '">' +
            '<input type="color" id="color-' + id + '" value="' + accent + '"' +
            ' class="stripe-color-input" title="Change colour"' +
            ' onclick="event.stopPropagation()"' +
            ' oninput="HomeScreen._saveColor(' + _attr(id) + ',this.value)"></div>' +
            '<div class="class-card-body">' +
            '<div class="class-card-name-group">' +
            '<div class="class-card-name">' + HomeScreen._esc(cls.name || id) + '</div>' +
            '<div class="class-card-id">Class ID: ' + HomeScreen._esc(id) + '</div>' +
            '</div>' +
            '<div class="class-card-footer">' +
            '<span class="class-card-stats">' + stats + '</span>' +
            '<span class="class-card-open">&#8250;</span>' +
            '</div></div></div>';
    },

    _saveColor: function(classroomId, color) {
        try { localStorage.setItem('lb-cls-color-' + classroomId, color); } catch(e) {}
        var stripe = document.getElementById('stripe-' + classroomId);
        if (stripe) stripe.style.background = color;
    },

    _showNewClassInfo: function() {
        EditorScreen._showToast("Add classrooms using the Classroom Manager.");
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
