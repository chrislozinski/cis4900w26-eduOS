function initDescriptionButton(info) {
    const showDescriptionButton = document.getElementById("show-description-button");
    if (!showDescriptionButton)
        return;
    if (!info.description || info.description.trim().length === 0) {
        showDescriptionButton.style.display = "none";
        return;
    }
    const descriptionModalOk = document.getElementById("description-modal-ok");
    const descriptionModal = document.getElementById("description-modal");
    const descriptionDimmer = document.getElementById("description-modal-dimmer");
    let isVisible = false;
    const focusTrap = (e) => {
        if (e.key === "Tab") {
            if (!descriptionModal.contains(document.activeElement)) {
                descriptionModalOk.focus();
            }
            e.preventDefault();
        }
        else if (e.key === "Escape" || e.key === "Esc") {
            setDescriptionVisible(false);
            showDescriptionButton.focus();
        }
    };
    const setDescriptionVisible = (visible) => {
        descriptionModal.style.display = visible ? "block" : "none";
        isVisible = visible;
        if (visible) {
            descriptionDimmer.style.display = "block";
            document.addEventListener("keydown", focusTrap);
            descriptionModalOk.focus();
        }
        else {
            descriptionDimmer.style.display = "none";
            document.removeEventListener("keydown", focusTrap);
        }
    };
    showDescriptionButton.addEventListener("click", function () {
        pxtTickEvent('share.showDescription', { target: "arcade" });
        setDescriptionVisible(true);
    });
    showDescriptionButton.addEventListener("keydown", fireClickOnEnter);
    descriptionModalOk.addEventListener("click", function () {
        setDescriptionVisible(false);
        showDescriptionButton.focus();
    });
    descriptionModalOk.addEventListener("keydown", fireClickOnEnter);
    descriptionDimmer.addEventListener("click", function () {
        setDescriptionVisible(false);
        showDescriptionButton.focus();
    });
}
/// <reference path="../node_modules/pxt-core/built/pxtlib.d.ts" />
/// <reference path="../node_modules/pxt-core/built/pxt.d.ts" />
window.initScriptPage = function init(info) {
    const editorEmbedURL = `/${info.versionSuffix}#sandbox:${info.projectId}`;
    const showCodeButton = document.getElementById("show-code-button");
    const showCodeButtonIcon = showCodeButton.getElementsByTagName("i").item(0);
    const showCodeButtonOverflow = document.getElementById("show-code-button-overflow");
    const editCodeButton = document.getElementById("editCodeButton");
    const editCodeButtonOverflow = document.getElementById("editCodeButton-overflow");
    const embedContainer = document.getElementById("embed-frame");
    initDescriptionButton(info);
    initOverflowMenu();
    let builtSimJSPromise = Promise.resolve(undefined);
    if (/prebuilt(?:[:=])1/i.test(window.location.href)) {
        const builtSimJsUrl = `/static/builtjs/${info.projectId}.json`;
        // kick off fetch immediately, no need to wait for ksrunnerready
        builtSimJSPromise = fetch(builtSimJsUrl)
            .then(resp => resp.json())
            .catch(e => {
            console.error("Failed to get prebuilt code");
            if (pxtTickEvent) {
                pxtTickEvent("share.prebuilt.missing");
            }
        });
    }
    // Kick off the target config fetch in the background
    initTickEventProxyAsync(info);
    ksRunnerReady(function () {
        runSimulator(embedContainer);
    });
    let isGame = true;
    // The edit code button is a link, so this click event is just for telemetry
    const onEditClick = () => {
        pxtTickEvent('share.editcode', { target: "arcade" });
    };
    const onShowCodeClick = () => {
        while (embedContainer.firstChild) {
            embedContainer.firstChild.remove();
        }
        // toggle game vs. code view
        if (isGame) {
            pxtTickEvent('share.showcode', { target: "arcade" });
            embedContainer.appendChild(createIFrame(editorEmbedURL));
            showCodeButton.title = "Show Game";
            showCodeButtonIcon.className = "fas fa-gamepad";
            showCodeButtonOverflow.textContent = "Show Game";
        }
        else {
            pxtTickEvent('share.showgame', { target: "arcade" });
            showCodeButton.title = "Show Code";
            showCodeButtonIcon.className = "fas fa-code";
            showCodeButtonOverflow.textContent = "Show Code";
            runSimulator(embedContainer);
        }
        isGame = !isGame;
    };
    editCodeButton.addEventListener("click", onEditClick);
    editCodeButtonOverflow.addEventListener("click", onEditClick);
    editCodeButton.addEventListener("keydown", fireClickOnEnter);
    showCodeButton.addEventListener("click", onShowCodeClick);
    showCodeButtonOverflow.addEventListener("click", onShowCodeClick);
    function runSimulator(container) {
        // yield to UI thread before compiling
        window.setTimeout(async function () {
            const builtSimJS = await builtSimJSPromise;
            const options = {
                id: info.projectId,
                builtJsInfo: builtSimJS,
            };
            console.log('simulating script');
            window.pxtConfig = { simUrl: window.pxt.webConfig.simUrl };
            const built = await pxt.runner.simulateAsync(container, options);
            const loader = document.getElementById("loader");
            if (loader)
                loader.remove();
            if (!builtSimJS) {
                builtSimJSPromise = Promise.resolve(built);
            }
            console.log('simulator started...');
            if (built.parts.indexOf("multiplayer") !== -1) {
                enableMultiplayerUI(info);
            }
        }, 0);
    }
    function createIFrame(src) {
        const iframe = document.createElement("iframe");
        iframe.className = "sim-embed";
        iframe.setAttribute("sandbox", "allow-popups allow-forms allow-scripts allow-same-origin");
        iframe.frameBorder = "0";
        iframe.src = src;
        return iframe;
    }
};
function fireClickOnEnter(e) {
    const charCode = (typeof e.which == "number") ? e.which : e.keyCode;
    if (charCode === 13 /* enter */ || charCode === 32 /* space */) {
        e.preventDefault();
        e.currentTarget.click();
    }
}
function initOverflowMenu() {
    const menuButton = document.getElementById("overflow-menu");
    const menuContentPane = document.getElementById("overflow-menu-content");
    const menuItems = [
        document.getElementById("show-code-button-overflow"),
        document.getElementById("editCodeButton-overflow"),
        document.getElementById("share-eval-button-overflow"),
        document.getElementById("multiplayer-share-button-overflow"),
    ];
    const onBlur = (e) => {
        const relatedTarget = e.relatedTarget;
        if (!menuContentPane.contains(relatedTarget) && relatedTarget !== menuButton) {
            setExpanded(false);
        }
    };
    for (const item of menuItems) {
        item.setAttribute("tabindex", "-1");
        item.addEventListener("keydown", fireClickOnEnter);
        item.addEventListener("click", () => {
            setExpanded(false);
            menuButton.focus();
        });
        item.addEventListener("blur", onBlur);
    }
    let isExpanded = false;
    const documentKeydownListener = (e) => {
        const activeItems = menuItems.filter(item => item.style.display !== "none");
        if (e.key === "Escape" || e.key === "Esc") {
            setExpanded(false);
            menuButton.focus();
        }
        else if (e.key === "ArrowDown" || e.key === "ArrowRight") {
            e.preventDefault();
            e.stopPropagation();
            const currentlyFocusedElement = document.activeElement;
            const currentIndex = activeItems.indexOf(currentlyFocusedElement);
            const nextIndex = (currentIndex + 1) % activeItems.length;
            activeItems[nextIndex].focus();
        }
        else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
            e.preventDefault();
            e.stopPropagation();
            const currentlyFocusedElement = document.activeElement;
            const currentIndex = activeItems.indexOf(currentlyFocusedElement);
            const nextIndex = (currentIndex - 1 + activeItems.length) % activeItems.length;
            activeItems[nextIndex].focus();
        }
    };
    const setExpanded = (expanded) => {
        menuContentPane.style.display = expanded ? "block" : "none";
        menuButton.setAttribute("aria-expanded", expanded ? "true" : "false");
        isExpanded = expanded;
        if (expanded) {
            menuItems[0].focus();
            document.addEventListener("keydown", documentKeydownListener);
        }
        else {
            document.removeEventListener("keydown", documentKeydownListener);
        }
    };
    menuButton.addEventListener("click", () => {
        setExpanded(!isExpanded);
    });
    menuButton.addEventListener("keydown", (e) => {
        const charCode = (typeof e.which == "number") ? e.which : e.keyCode;
        if (charCode === 13 /* enter */ || charCode === 32 /* space */ || charCode === 40 /* down arrow */) {
            e.preventDefault();
            setExpanded(!isExpanded);
        }
    });
}
if (!window.multiplayerInitialized) {
    window.multiplayerInitialized = false;
}
function enableMultiplayerUI(info) {
    if (window.multiplayerInitialized)
        return;
    window.multiplayerInitialized = true;
    pxtTickEvent('share.isMultiplayerGame', { target: "arcade" });
    const presenceBar = document.getElementById("presence-bar");
    if (presenceBar) {
        initPresenceBar();
        presenceBar.style.display = "block";
    }
    const onClick = function () {
        pxtTickEvent('share.multiplayerShareClick', { target: "arcade" });
        const domain = pxt.BrowserUtils.isLocalHostDev() ? "http://localhost:3000" : "";
        const multiplayerHostUrl = `${domain}${pxt.webConfig.relprefix}multiplayer?host=${info.projectId}`;
        window.open(multiplayerHostUrl, "_blank");
    };
    // icon button
    const shareButton = document.getElementById("multiplayer-share-button");
    if (shareButton) {
        shareButton.addEventListener("click", onClick);
        shareButton.style.display = "flex";
    }
    // overflow menu button
    const overflowButton = document.getElementById("multiplayer-share-button-overflow");
    if (overflowButton) {
        overflowButton.addEventListener("click", onClick);
        overflowButton.style.display = "block";
    }
    // fix the aria-setsize for the overflow menu items since we're adding an additional item
    const overflowItems = document.querySelectorAll(".common-menu-dropdown [aria-setsize]");
    overflowItems.forEach(item => {
        item.setAttribute("aria-setsize", "4");
    });
    window.addEventListener('message', function (ev) {
        if (ev.data && ev.data.type === "status" && ev.data.state === "running") {
            const iframe = document.getElementsByTagName("iframe").item(0);
            if (iframe) {
                setActivePlayer(1, iframe);
            }
        }
    });
    function initPresenceBar() {
        for (let i = 0; i < 4; i++) {
            const button = document.getElementsByClassName("player-" + (i + 1)).item(0);
            button.addEventListener("click", () => {
                const iframe = document.getElementsByTagName("iframe").item(0);
                if (iframe) {
                    setActivePlayer(i + 1, iframe);
                    iframe.focus();
                }
            });
        }
    }
    function setActivePlayer(playerNumber, iframe) {
        const setSlotMsg = {
            type: "setactiveplayer",
            playerNumber: playerNumber,
        };
        const connectionMsg = {
            type: "multiplayer",
            content: "Connection",
            slot: playerNumber,
            connected: true,
        };
        iframe.contentWindow.postMessage(setSlotMsg, "*");
        iframe.contentWindow.postMessage(connectionMsg, "*");
    }
}
async function initTickEventProxyAsync(info) {
    let shareLinkIsApproved = false;
    // This promise is defined in pxt/docfiles/targetconfig.html
    const targetConfig = await pxtTargetConfigPromise;
    const approvedShareLinks = targetConfig && targetConfig.shareLinks && targetConfig.shareLinks.approved;
    if (approvedShareLinks && approvedShareLinks.indexOf(info.projectId) >= 0) {
        // This share link has been allow listed; remove cookie banner and allow sending of tick events
        shareLinkIsApproved = true;
        const abuseMessage = document.getElementById("abuse-message");
        if (abuseMessage) {
            abuseMessage.remove();
        }
        pxtTickEvent('approved.shareurl.loaded', { shareurl: info.projectId, target: "arcade", cookie: "true" });
    }
    // While we have the target config, check if we should show the eval button
    const evalEnabled = targetConfig && targetConfig.teachertool && targetConfig.teachertool.showSharePageEvalButton;
    if (!evalEnabled) {
        const evalButton = document.getElementById("share-eval-button");
        if (evalButton) {
            evalButton.remove();
        }
    }
    // Proxy tick events from the simulator
    if (shareLinkIsApproved) {
        window.addEventListener('message', function (ev) {
            const d = ev.data;
            if (d.type == "messagepacket" && d.channel == "tick-event" && d.data) {
                let unpackedData = "";
                for (let i = 0; i < d.data.length; ++i)
                    unpackedData += String.fromCharCode(d.data[i]);
                try {
                    const data = JSON.parse(unpackedData);
                    data["shareurl"] = info.projectId;
                    data["target"] = "arcade";
                    data["cookie"] = "true";
                    pxtTickEvent('simulator.user.tick', data);
                }
                catch (e) { /** failed to parse tick from game **/ }
            }
        });
    }
}
