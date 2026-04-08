# MakeCode Audio — Comprehensive Diagnostic Report

---

## The Two Bugs

### Bug A: Block snap/click sounds never play
When Blockly blocks are connected, there should be a click sound from `/blockly/media/click.wav` (and `.mp3`, `.ogg`). It has **never** worked.

### Bug B: Simulator freezes ~10 seconds on first audio block
First time an audio or sound-effect block runs in the simulator, the entire app freezes and becomes unresponsive for ~10 seconds. After that one freeze, it works for the rest of the session. Opening Waterfox and playing any audio before opening the simulator eliminates the freeze entirely.

---

## Confirmed Facts — Code Paths Traced

### Bug A — Snap sounds

**Files:** `src/debian-base1/widgets/makecode/makecode-static/blockly/media/`
- `click.mp3`, `click.wav`, `click.ogg`, `delete.*`, `disconnect.*` — all present

**How Blockly loads and plays them:**

1. `main.js:839732` — Blockly workspace is initialized with:
   ```js
   { sounds: !0, media: pxt.webConfig.commitCdnUrl + "blockly/media/" }
   ```

2. `index.html:5261` — The offline static build hardcodes `commitCdnUrl: "/"`, so the media path is `"/blockly/media/"`. Resolved against `http://127.0.0.1:PORT`, this becomes `http://127.0.0.1:PORT/blockly/media/click.wav` etc. **These paths serve correctly from our static server — confirmed the files exist.**

3. `main.js:2135455` — Because `hasSounds=true`, `sa(pathToMedia, workspace)` is called:
   ```js
   sa = function(e, t) {
     const i = t.getAudioManager();
     i.load([e+"click.mp3", e+"click.wav", e+"click.ogg"], "click");
     i.load([e+"disconnect.wav", ...], "disconnect");
     i.load([e+"delete.mp3", ...], "delete");
     // register preload trigger on first pointermove / touchstart
     r.push(m(document, "pointermove", null, n, !0));
     r.push(m(document, "touchstart",  null, n, !0));
   }
   ```

4. `main.js:2463301` — `AudioManager.load()` (class `Pf`):
   ```js
   load(e, t) {
     var n = new globalThis.Audio();           // test canPlayType
     for (let t = 0; t < e.length; t++) {
       const r = e[t], o = r.match(/\.(\w+)$/);
       if (o && n.canPlayType("audio/" + o[1])) {  // picks first supported format
         var i = new globalThis.Audio(r); break;
       }
     }
     i && this.sounds.set(t, i);               // stores Audio element by key "click" etc.
   }
   ```
   Tries mp3 first, then wav, then ogg. Picks first where `canPlayType` returns non-empty.

5. `main.js:2463301` — `AudioManager.preload()` fires on first pointermove:
   ```js
   e.volume = 0.01;
   const t = e.play();
   t.then(e.pause).catch(function(){});  // note: e.pause not bound to e — fails silently
   ```

6. `main.js:2114487` — `Fo()` called when block snaps, calls:
   ```js
   t.getAudioManager().play("click")
   ```
   Which does:
   ```js
   (n = n.cloneNode()).volume = 1;
   n.play();   // NO catch handler — silent failure
   ```

**What is ruled out for Bug A:**
- URL path is correct ✓
- Files exist on server ✓
- `hasSounds` is true ✓
- `commitCdnUrl` is `"/"` not a CDN URL ✓
- `set_media_playback_requires_user_gesture(False)` is set (though see unknowns)

---

### Bug B — Simulator freeze

**Files:**
- `src/debian-base1/widgets/makecode/makecode-static/simulator.html` — iframe page
- `src/debian-base1/widgets/makecode/makecode-static/pxtsim.js` — loaded by simulator.html
- `src/debian-base1/widgets/makecode/makecode-static/sim.js` — loaded by simulator.html
- `src/debian-base1/widgets/makecode/makecode-static/common-sim.js` — contains `AudioContextManager`

**How the simulator plays audio:**

1. `simulator.html` is loaded in an `<iframe>` by MakeCode's main editor when the user runs their program
2. `common-sim.js:3070` — When a sound block runs, `pxsim.AudioContextManager.playInstructionsAsync()` is called
3. `sim.js:170` — `pxsim.AudioContextManager.mute(false)` is called at startup
4. `sim.js:3488` — `pxsim.AudioContextManager.tone(frequency, 1)` for tone generation
5. All of these eventually create or resume an `AudioContext`

**The Waterfox observation — most important clue:**
Opening Waterfox (a completely separate OS process) and playing any audio permanently fixes the simulator freeze for the rest of the session. This is a **system-level** observation. It means:
- The fix is not inside WebKit or MakeCode's JS
- Once **any** process on the system triggers audio through PipeWire/GStreamer, the channel is "live"
- All subsequent processes (including WebKit) connect to that already-live channel instantly instead of waiting

**What is ruled out for Bug B:**
- Codec issues — game sounds work fine after the first freeze ✓
- Main editor audio — the sound effect editor (note preview) works immediately ✓
- It's not a JS thread block — it freezes the entire GTK window, including native widgets, meaning it's blocking at the GLib/GStreamer native level

---

## Root Cause Theories

### Bug A — Why snap sounds never work

**Theory A1 (most likely): `canPlayType()` returns empty for all three formats**
If `canPlayType("audio/mp3")`, `canPlayType("audio/wav")`, and `canPlayType("audio/ogg")` all return `""`, then `i` is never assigned and `this.sounds.set(t, i)` is never called. `play("click")` finds nothing in the map and silently does nothing. This would mean the Audio elements never even get created.

Why this might happen: `canPlayType` in WebKit2GTK queries GStreamer's plugin registry. If GStreamer's plugin scanner runs before the relevant plugins are registered in the user's session environment, it might report false negatives. This is a known issue in some WebKit2GTK builds.

**Theory A2: Autoplay policy blocking `play()`**
`set_media_playback_requires_user_gesture(False)` is in a `try/except: pass` block in `makecode-app.py:730`. If WebKit2GTK 4.1's Python GI bindings don't expose this method (or it was renamed), the exception is swallowed and the setting is never applied. WebKit then requires a genuine user gesture (click/keydown, NOT pointermove) before `HTMLAudioElement.play()` is allowed. The preload fires on `pointermove` (not a gesture), gets rejected, the sounds never get preloaded, and subsequent `play()` calls on unpreloaded Audio elements also fail.

**Theory A3: GStreamer pulsesink fails silently on first HTMLAudioElement play**
HTMLAudioElement in WebKit2GTK may use `autoaudiosink` → `pulsesink` → PipeWire-Pulse rather than `pipewiresink`. If the pulsesink path has its own initialization delay (separate from AudioContext's pipewiresink path), then `play()` returns a rejected Promise. Since Blockly's `play()` has no catch handler, this fails silently every time.

### Bug B — Why the simulator freezes

**Theory B1 (most likely): xrdp audio channel not established when first WebKit process connects**

The audio pipeline is: GStreamer → PipeWire → `pipewire-module-xrdp` → RDP audio channel → RDP client (user's Remote Desktop app).

`pipewire-module-xrdp` bridges PipeWire to the xrdp audio subsystem, but the actual RDP audio channel is only opened by the **RDP client** (the remote desktop viewer). This negotiation happens asynchronously after the RDP session connects. `start-audio.sh` loads the module and immediately exits, but the channel may not be fully established for several seconds.

When any process first tries to play audio through PipeWire → xrdp → RDP, it blocks waiting for the channel to be ready (~10 seconds). Once it's established, all subsequent connections are instant — explaining both why it fixes itself after the first freeze and why Waterfox opening it first makes everything fast.

**Theory B2: Separate WebKit WebContent process per iframe**
WebKit2GTK runs each web page (and potentially each iframe from a different origin — though in our case the simulator is same-origin) in a separate `WebKitWebProcess`. Each process has its own GStreamer instance. Even if the main editor's GStreamer connection is established, the simulator iframe's process needs to establish its own. This would explain why our JS pre-warm in the main window doesn't help the simulator.

Whether the simulator iframe shares a WebContent process with the main page or gets its own is a WebKit2GTK implementation detail we haven't confirmed.

---

## Solutions Tried and Why Each Failed

### 1. JS AudioContext pre-warm (async, `setTimeout(0)`)
**What it did:** Created `new AudioContext()` in a setTimeout callback, called `resume()`, set a `_pwReady` flag when done. Wrapper intercepted `new AudioContext()` calls and returned the pre-warmed context only if `_pwReady` was true.

**Why it failed:** The `setTimeout(0)` delays the warm-up start. The simulator could load and the user could add an audio block within the same ~10-second window that the warm-up was trying to complete. Since `_pwReady` was false, sim.js got a fresh AudioContext from the else branch, which also triggered its own 10-second connection.

### 2. JS AudioContext pre-warm (synchronous, no `_pwReady` guard)
**What it did:** Fired pre-warm synchronously (no setTimeout), handed back `_pw` immediately even while `resume()` was in-flight.

**Why it failed:** Even if sim.js gets the pre-warmed context, the 10-second block still happens — `resume()` is already in-flight on that context, but native GStreamer still has to wait for the xrdp channel. The context being "shared" doesn't skip the xrdp negotiation; it just means one thread waits instead of two. The freeze still occurs because the GLib/GStreamer event loop is blocked at the native level.

### 3. JS HTMLAudioElement silent pre-warm (playing `click.wav` at volume 0)
**What it did:** At script injection time, created `new Audio(L+'/blockly/media/click.wav')`, set volume to 0, called `play()`.

**Why it failed:** Uncertain — either (a) autoplay policy blocked the play() call before the user interacted, (b) canPlayType returned empty so the audio never loaded, or (c) it actually did warm the pulsesink but that path doesn't help the simulator freeze (which uses AudioContext/pipewiresink, not pulsesink).

### 4. `gst-launch-1.0` in `start-audio.sh`
**What it did:** After `load_pw_modules.sh`, ran:
```bash
gst-launch-1.0 -q audiotestsrc wave=4 num-buffers=1 ! pipewiresink 2>/dev/null || true
```

**Why it likely failed:** `load_pw_modules.sh` loads the `pipewire-module-xrdp` PipeWire module, but that module bridges to the xrdp audio channel. The xrdp audio channel is opened by the **RDP client** asynchronously after the session starts — `load_pw_modules.sh` returning does not mean the channel is open. `gst-launch` then tries `pipewiresink`, finds no active xrdp audio sink yet, fails silently (masked by `|| true`), and establishes nothing. By the time the user opens MakeCode, the gst-launch warmup has produced no lasting effect.

Additionally: even if `gst-launch` had succeeded, it runs and exits. GStreamer connections don't persist after the process exits. When WebKit's process then creates its own GStreamer pipeline, it makes a fresh connection anyway.

### 5. Codec additions (`gstreamer1.0-plugins-good`, `gstreamer1.0-plugins-bad`, `gstreamer1.0-libav`)
**What it did:** Ensured AAC (M4A), MP3, OGG decoders are available.

**Effect:** Helped in that main editor audio (note preview, sound effect editor) now works. Did not fix snap sounds or simulator freeze because those are pipeline connection problems, not codec problems.

### 6. `canPlayType()` monkeypatch shim (JS UserScript injection)
**What it did:** Prepended a JS IIFE to the CDN-rewrite UserScript that patches `HTMLAudioElement.prototype.canPlayType` to return `"probably"` for `audio/mpeg`, `audio/mp3`, `audio/wav`, and `audio/ogg`. Injected at `UserScriptInjectionTime.START` into `ALL_FRAMES`.

**Why it failed (Bug A):** After applying this, snap sounds still did not play. The shim confirmed and addressed Theory A1 — `canPlayType` was returning `""` so Blockly's `load()` never stored Audio elements. But fixing that alone was not sufficient. The Audio elements are now created, but `play()` is still being silently rejected. This points to Theory A2 (autoplay policy) as the **remaining primary blocker**: `set_media_playback_requires_user_gesture(False)` is inside a `try/except: pass` and may not be taking effect, so WebKit still blocks `HTMLAudioElement.play()` unless the page has received a genuine click/keydown gesture. Blockly's preload fires on `pointermove` which does not satisfy browser autoplay policy.

**Scope:** Bug A only. Never addressed Bug B.

### 7. AudioContext polyfill replacing `window.Audio` (JS UserScript injection)
**What it did:** Injected an `AudioShim` class at `UserScriptInjectionTime.START` that replaced `window.Audio`/`globalThis.Audio`. The shim used `fetch(url)` + `AudioContext.decodeAudioData()` to load audio files and `createBufferSource()` to play them, bypassing HTMLAudioElement entirely.

**Why it failed:** The polyfill was architecturally sound but did not address the real root cause. The real problem was not that HTMLAudioElement's `play()` was being rejected — it was that `isSafari()` in sim.js was returning `true` for WebKit2GTK (because its UA contains the string "Safari"), causing `AudioContextManager.mute(true)` at simulator startup. The polyfill fixed the Blockly `Audio` element path but had no effect on the simulator's muted AudioContext.

**Scope:** Bug A targeted. All code reverted.

### 8. `gst-launch` with xrdp sink polling (`start-audio.sh`)
**What it did:** Added a `wpctl status | grep -q "xrdp"` poll loop (60 × 0.5s) to wait for the xrdp sink before running `gst-launch-1.0 -q audiotestsrc wave=silence num-buffers=10 ! pipewiresink`.

**Why it failed:** Did not fix the freeze because the root cause was not the xrdp channel timing — it was the `isSafari()` false positive in sim.js causing AudioContextManager to mute itself. Even with a correctly-initialized xrdp channel, the simulator would still freeze because its AudioContext was being put into a muted/suspended state at startup and only resumed when the user first hit an audio block.

**Scope:** Bug B targeted. All code reverted.

### 9. Persistent GStreamer pipeline via Python GI (`gi.repository.Gst`)
**What it did:** Added `gi.require_version('Gst', '1.0')` and `from gi.repository import Gst` at the top of `makecode-app.py`, then created a `Gst.parse_launch("audiotestsrc wave=silence is-live=true ! pulsesink")` pipeline in `MakeCodeWindow.__init__` and set it to `PLAYING` state.

**Why it failed:** The Dockerfile did not include `gir1.2-gstreamer-1.0` (the GObject Introspection typelib for GStreamer). `gi.require_version('Gst', '1.0')` at module level raised a `ValueError` before `main()` ran, crashing the entire application. MakeCode stopped launching entirely. **The persistent pipeline approach was never actually tested** — it was invalidated by a packaging error, not by the concept being wrong. The approach itself (a long-lived process holding the xrdp channel open) remains a valid theory (see Step 7 in Potential Next Steps), but requires either installing `gir1.2-gstreamer-1.0` in the Dockerfile or using a different mechanism.

**Scope:** Bug B only. All code reverted.

---

## Fixes Applied

### Fix for Bug B — `sim.js:763` — `isSafari()` false positive
WebKit2GTK's user agent string contains the substring `"Safari"` (e.g.
`Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15`).
The `isSafari()` function tested `/(Macintosh|Safari|iPod|iPhone|iPad)/i` — the `Safari` alternative
matched WebKit2GTK, causing `shouldShowMute()` to return `true`, which triggered
`AudioContextManager.mute(true)` at simulator startup. This suspended the AudioContext before
any audio block ran. When the first audio block executed, resuming the suspended AudioContext
triggered the native PipeWire negotiation on the GTK main thread → 10-second freeze.

**Fix:** Removed `Safari` from the isSafari regex. Real Safari on macOS still matches via
`Macintosh`; iOS Safari still matches via `iPhone|iPod|iPad`. WebKit2GTK on Linux (which has
`X11; Linux` in its UA but none of those strings) no longer matches.

```
sim.js:763  /(Macintosh|iPod|iPhone|iPad)/i   (was: /(Macintosh|Safari|iPod|iPhone|iPad)/i)
```

### Fix for Bug A — `main.js` — `AudioManager.load()` canPlayType guard
`AudioManager.load()` called `n.canPlayType("audio/"+ext)` before creating any `Audio` element.
In WebKit2GTK, `canPlayType()` returns `""` for all formats (GStreamer plugin registry timing
issue), so no `Audio` element was ever stored and snap sounds silently never played.

**Fix:** Removed the `canPlayType` guard. The loop now always picks the first matching file
extension and creates the `Audio` element unconditionally. The `.mp3` files will be attempted
first; `gstreamer1.0-plugins-good` (already in the Dockerfile) handles MP3 decoding.

```
main.js  if(o){var i=new globalThis.Audio(r);break}
         (was: if(o&&n.canPlayType("audio/"+o[1])){var i=new globalThis.Audio(r);break})
```

---

## External Research Findings

### R1: Browser Autoplay Policy (MDN)
"Web Audio contexts are generally blocked if playback is initiated programmatically without a user gesture." Applies to both `HTMLAudioElement.play()` and `AudioContext.resume()`. In practice, browsers require a `click`, `keydown`, or `touchstart` event — **`pointermove` does not count**. Blockly's preload (`AudioManager.preload()`) fires on `pointermove`, which means it does not satisfy autoplay policy. If `set_media_playback_requires_user_gesture(False)` is not taking effect, every `play()` call — including the preload and all snap sounds — is silently rejected as a Promise rejection with no catch handler.

**Relevance:** Directly explains why canPlayType shim (#6 above) fixed `load()` but not `play()`. Theory A2 is now the highest-priority suspect for Bug A.

### R2: Blockly Injection `sound: false` Option
Blockly supports a `sound: false` injection option to disable UI sounds entirely (per Neil Fraser). MakeCode's build sets `sounds: !0` (true) so this is already enabled on their side. The inverse implication — that `sound: true` could "re-enable" sounds — is not actionable since sounds are already enabled. The relevant note is that if blockly/media/ assets fail to load, sounds are silently absent. Our files exist and paths are correct, so this is ruled out.

**Relevance:** Ruled out as a cause. Already confirmed assets exist and are served correctly.

### R3: Simulator Memory Leak (GitHub #3931)
Each compile (triggered on every block edit) leaks memory. Repeated drag-and-drop plus screen/sound effects could exhaust resources and cause stalls.

**Relevance:** Could contribute to degraded performance over a session but does not explain the consistent ~10-second first-freeze which is clearly the xrdp channel negotiation (confirmed by Waterfox observation). Low priority.

### R4: Audio Static/Distortion (Community Report)
A user (PixelDoodle) reported arcade audio "slowly turning to static" then muting. Hints at a Web Audio mixing or buffer bug.

**Relevance:** Different symptom from our bugs. Not currently observed. Low priority.

---

## What Is Still Unknown (Needs Investigation)

1. **~~Does `canPlayType()` actually return anything in this build?~~** ✓ **ANSWERED** — It returns `""` for all formats. Confirmed by the fact that the canPlayType shim (#6) enabled Blockly's `load()` to proceed (Audio elements created), but `play()` still fails. The shim is no longer in the code because it alone was insufficient.

2. **Is `set_media_playback_requires_user_gesture(False)` actually taking effect?** ⚠️ **NOW THE #1 PRIORITY FOR BUG A.** The call is inside `try/except: pass` at `makecode-app.py:730`. If the WebKit2GTK 4.1 GI bindings don't expose this method (or it was renamed), the exception is swallowed and autoplay policy is never relaxed. Combined with Research Finding R1, this is the most likely remaining root cause of Bug A.

3. **Does the simulator iframe share a WebContent process with the main editor?** If same-origin iframes share a process in WebKit2GTK 4.1, a main-page pre-warm WOULD help the simulator. If not, it can't. Never confirmed.

4. **When exactly is the xrdp audio channel ready?** Is there a PipeWire event, node, or pw-cli query that tells us the xrdp sink is active and accepting streams? If yes, `start-audio.sh` could poll for it instead of sleeping.

5. **What GStreamer sink does WebKit2GTK actually use?** `pipewiresink` (direct PipeWire), `pulsesink` (PipeWire-Pulse compat layer), or `autoaudiosink` (whatever ranks highest)? This determines which pipeline to warm.

---

## Potential Next Steps — Ordered by Confidence

### Step 1 (~~Diagnostic~~ ✓ DONE): `canPlayType` returns `""` for all formats — confirmed
Theory A1 confirmed via canPlayType shim test (#6). Audio elements are now being created by Blockly's `load()`. Shim itself was insufficient and removed. Root cause has shifted to Theory A2.

### Step 2 (Fix for Bug A — highest priority): Verify and fix `set_media_playback_requires_user_gesture`
**This is the most likely remaining cause of Bug A.** The call at `makecode-app.py:730` is inside `try/except: pass` and may be silently failing. Two sub-steps:
- a) Remove the `try/except: pass` and log whether the call succeeds or raises — if it raises, the autoplay policy is never relaxed.
- b) If it's failing, find the correct API: in WebKit2GTK 4.1 it may be exposed differently. The correct GI property may be `webkit_settings_set_media_playback_allows_inline` or similar. Cross-reference the WebKit2GTK 4.1 `.gir` file.
- c) If the API truly doesn't exist in this build, the fallback is a UserScript that hooks the first `click` event on the page to call `.play()` on all stored Audio elements, then immediately `.pause()` — this unlocks autoplay policy for all subsequent plays without audible output.

### Step 3 (Diagnostic): Confirm whether simulator shares a WebContent process
Run the container, open MakeCode, add an audio block, then run `ps aux | grep WebKit` on the host. Count the `WebKitWebProcess` instances — one means shared, two means separate. Determines whether any main-page warmup can ever help the simulator.

### Step 4 (Fix for Bug B): Add a real wait for the xrdp audio sink in `start-audio.sh`
Instead of a fixed sleep or one-shot gst-launch, poll `pactl list sinks | grep xrdp` or `pw-cli list-objects | grep xrdp` to detect when the xrdp sink actually exists. Only then attempt audio playback. This attacks the root cause (xrdp channel not yet established) with correct timing rather than a race.

### Step 5 (Fix for Bug B, direct): Modify `simulator.html` to pre-warm AudioContext at load time
Since `simulator.html` is our served static file, add a `<script>` tag before `pxtsim.js` that immediately creates an `AudioContext` and calls `resume()`. The 10-second wait still happens, but it starts the moment `simulator.html` loads (before the user adds any block), not when the first audio block runs. Net effect: freeze moves from "user's first interaction" to "invisible background on page load."

### Step 6 (Fix for Bug B, system-level): Persistent GStreamer pipeline in the Python app
Add `gir1.2-gstreamer-1.0` to the Dockerfile. Then in `MakeCodeWindow.__init__`, create and hold a `Gst.parse_launch("audiotestsrc wave=silence is-live=true ! pulsesink")` pipeline at `PLAYING` state. This was attempted but never ran due to missing package. The concept is valid — mimics what Waterfox does. Requires Step 4's timing fix to also be solved (pipeline needs the xrdp sink to exist first).

### Step 7 (Bug A fallback): Replace `globalThis.Audio` with an AudioContext-backed shim
Inject a UserScript that replaces `globalThis.Audio` with a shim that decodes and plays via `AudioContext`+`AudioBuffer` instead of a native `<audio>` element. AudioContext already works (once warmed). Bypasses the entire pulsesink/HTMLAudioElement/autoplay pipeline. High complexity but guaranteed to work if AudioContext works. Only pursue if Steps 2–3 fail to resolve Bug A.

---

## Files of Interest

| File | Relevance |
|------|-----------|
| `src/debian-base1/widgets/makecode/makecode-app.py:923` | `_apply_offline_cdn_rewrite()` — where UserScript is injected |
| `src/debian-base1/widgets/makecode/makecode-app.py:719` | `settings.set_media_playback_requires_user_gesture(False)` — silent try/except |
| `src/debian-base1/config/launcher/start-audio.sh` | Session audio startup — where system-level warmup would go |
| `src/debian-base1/Dockerfile:75` | GStreamer package installs |
| `makecode-static/main.js:2463301` | Blockly `AudioManager` class (`Pf`) — load/preload/play |
| `makecode-static/main.js:2135455` | `sa()` — where Blockly audio is initialized |
| `makecode-static/main.js:2114487` | `Fo()` — where `play("click")` is called on block snap |
| `makecode-static/simulator.html` | Simulator iframe — could add inline script here |
| `makecode-static/common-sim.js:3070` | `AudioContextManager.playInstructionsAsync()` — simulator audio entry point |
