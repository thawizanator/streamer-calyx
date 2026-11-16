# Streamer Calyx — Project Roadmap 🗺️

Welcome to the development roadmap for **Streamer Calyx** (formerly *HotKey Overlay Alert*). This document tracks completed milestones, current progress, and upcoming features designed to make this the ultimate backstage broadcast suite for streamers, co-hosts, and remote directors.

---

## 🧭 Release Architecture & Branches

- **`main` Branch**: Tracks stable production releases (currently **`v3.0.2`**).
- **`develop` Branch**: Tracks active feature branches, updates, and previews (currently **`v4.0.0-dev`**).

---

## ✅ Completed Milestones

### Phase 1: Modern Left Sidebar Navigation Shell (`v3.0.0-alpha`) — *Completed*
- Replaced classic vertical tab widget with a scalable, modern **Left Sidebar Shell** (`SettingsWindow`).
- Grouped views into logical categories: **DISPLAY & ALERTS**, **STREAM TOOLS**, and **APP & CONFIG**.
- Preserved existing views: Main Overlay, Monitor Setup, Alert Overlay, Twitch Macros, and System & Logs.
- Full Light and Dark theme synchronization with dynamic OS color scheme detection.

### Phase 2: Chronos Timers Engine & OBS Integration (`v3.0.0-beta.1`) — *Completed*
- Multi-timer engine supporting **Countdowns**, **Stopwatches**, and **Interval Timers**.
- Real-time OBS / Streamlabs file-based text sync (`timer_display.txt`) with custom templates.
- Audio alerts with synthesized chime beeps and custom WAV audio playback.
- Configurable completion actions, custom banner toasts, and independent timer state preservation.

### Phase 3: Rotating Text & Trivia Cycler Engine (`v3.0.0-beta.2`) — *Completed*
- Timed line rotator for stream trivia, community rules, sponsor messages, and social links.
- Interactive **Trivia Q&A Mode** with customizable question-to-answer reveal countdowns.
- Real-time OBS / Streamlabs output sync with prefix/suffix formatting.
- Compacted UI item rows and collapsible sidebar navigation (`◀` / `▶` and `Ctrl+B`) fitting compact and portrait displays (Monitor #3).

### Phase 3.5: Multi-Monitor Cross-DPI Handling & Traceability — *Completed*
- Unified multi-monitor virtual coordinate space via **System DPI Awareness** (`windows:dpiawareness=1`) and user-selectable toggle under **Monitor Setup**.
- Integrated Git commit hash (`get_build_commit()`) across sidebar footer, window titles, Updates tab, and diagnostic bug report templates.

### Phase 4.1: OBS Studio & Streamlabs Desktop WebSocket Gateway — *Completed*
- **WebSocket Integration**: Direct low-latency connection to local OBS Studio and Streamlabs Desktop via OBS WebSocket protocol (`ws://localhost:4455`).
- **Scene & Source Control**: Instantly switch scenes, toggle display/browser sources, mute/unmute audio tracks, and trigger transitions.
- **LAN & Multi-PC Verification**: Verified operational across local PCs connected to the same LAN.

### Phase 4.2: Stream Director, Remote P2P WebRTC & Fine-Grained Permissions (`v3.0.0-beta.3`) — *Completed*
- **P2P WebRTC Data Channels + Signaling Bouncer Proxy**: Encrypted WAN remote control between streamer and remote director with zero port forwarding.
- **Twitch Identity Whitelist & Pairing Passkeys**: Automated handshake combining Twitch username verification with AES-256 encrypted pairing keys.
- **3-Tab Layout & Conditional Visibility**: Dedicated tabs for *Scenes & Controls*, *Audio Mixer*, and *Remote Co-Host* (automatically shown/hidden based on Streamer Mode).
- **Granular Windows-Style User Permissions Matrix**: Element-by-element permission checklist per remote director (allowed scenes, mute controls, volume adjustments, or full control).
- **Instant Visual Locking**: Gated controls display `[🔒 LOCKED]` badge and disabled state on initial connect without requiring first click.
- **Smooth Fader Dragging & Non-Destructive Layout**: Custom `SmoothSlider` with 1:1 mouse tracking and in-place widget updates eliminating flickering, sizing glitches, and mouse-grab drops.
- **Live Peer Testing Passed**: Successfully validated in live peer-to-peer remote testing with co-host `@purplen3rd`.
- **Identity Rebrand**: Transitioned full project identity to **Streamer Calyx** (`StreamerCalyx.exe`, `%APPDATA%\StreamerCalyx` zero-downtime auto-migration).

---

### Phase 5: Unified Hotkey Center, 5 Faders, 8-Item Pools, Per-Scene Shortcuts & Peripheral Support (`v3.0.0-beta.4.2`) — *Completed*
- **Central Hotkey Manager Tab**: A dedicated view (**Hotkeys & Peripherals**) in the navigation sidebar displaying an expandable accordion drawer interface for all 22 stream actions with zero horizontal clipping.
- **Native Zero-Dependency XInput Gamepad Support**:
  - Low-latency background controller polling via Windows `xinput1_4.dll` (with ordinal 100 for central Xbox Guide button support).
  - Captures inputs globally across games and full-screen streaming setups (<0.1% CPU).
  - **Streamer Chords & Hold Delays**: Supports combination buttons (e.g., `LT + LS Click + Y`, `LB + RB`, `Back + Y`) and configurable hold thresholds (0.5s, 0.75s, 1.0s) so active gameplay controls are shielded.
  - **Peak Chord Accumulator & Release Shielding**: Multi-button combos persist through sequential button releases without accidental single-button trigger misfires.
- **2-Row Live Controller Visualizer HUD & 1-Click Recorder**: Real-time HUD lighting up physical buttons as pressed, fitting comfortably within collapsed 570px windows (>140px clearance).
- **Multi-Device Mouse & Keyboard Hooks**: Full global mapping for Mouse 3, 4, 5, modifiers, and keyboard keys.
- **Expanded Stream Director Audio Mixing & Pools**:
  - 5 active volume faders with responsive dock layout.
  - 8-item preselected pools for Scenes, Audio Mutes, and Volume Faders with live dock slot management.
  - Granular permissions matrix allowing or denying co-hosts access to individual scenes (1..8), mutes (1..8), and faders (1..8) with BouncerValidator security.
- **Per-Scene Shortcuts & SLOBS Hotkey Customization**:
  - Configure up to 4 custom shortcuts and hotkeys per scene in Settings (`SceneEditDialog` and Director Tab Toggles overview).
  - Dynamic dock hotkey population reflowing per scene (and auto-hiding for scenes with 0 shortcuts).
  - Dedicated **`SLOBS HOTKEYS`** card with independent view toggles (`Ctrl+Num6` for SandMan View and `Ctrl+Num7` for Legal-View).
  - Universal Win32 hardware scan code and virtual key dispatcher supporting arbitrary modifier combinations and keys.
  - 2-row Scene Selection grid on dock cutting section width by >400px with solid active accent fill outline and luminance-based text contrast.
  - Scene-aware dynamic audio & volume fader filtering based on live Streamlabs Desktop SceneItem presence.

---

### Phase 6: Soundboard Deck, Troll Shield & Auto-Clip Stream Markers (`v3.0.0-beta.5.0`) — *Completed*
- **Standalone Soundboard Engine**: Local audio effect player and production audio routing with zero external dependencies.
- **SandMan Anti-Spam Troll Shield**: Rate-limiting rapid-fire playback, panic lock, and loud alarm buzzer protection for remote co-host sound triggering.
- **Auto-Clip & Stream Markers Engine**: Real-time microphone/VoiceMeeter audio monitoring, 10-second rolling baseline, 40-segment LED VU meter, Twitch stream marker dispatcher, and 60-second clip window logging (40s pre / 20s aftermath).
- **WASAPI 32-Bit IEEE Float PCM Decoding**: Native Windows 11 and VoiceMeeter VAIO audio support with zero digital distortion.
- **Hardware/Virtual Input Gain Trim**: Direct in-app gain slider (25% to 200%) with 1-click reset button.
- **Streamer Mode Gating**: Automatically pauses audio capture and dims controls when Streamer Mode is disabled.
- **Audio Input Diagnostics Suite**: Privacy-safe 5-second acoustic calibration benchmark with copyable reports and bug report attachment.

---

### Phase 7: Optimization, Debloating Architecture & NSIS Installer (`v3.0.0`) — *Completed*
- **Binary Debloating & Trimming**:
  - Excluded unused Qt6 modules (`Qt6Qml`, `Qt6Quick`, `Qt6Designer`, `Qt6Pdf`, `Qt6VirtualKeyboard`).
  - Stripped `opengl32sw.dll` (19.68 MB) software OpenGL fallback and transitively pulled `numpy`/`scipy` dependencies.
  - Slashed installer footprint by ~45% down to **~52 MB**.
- **Dual-Distribution Packaging Pipeline**:
  - **NSIS Modern Installer (`StreamerCalyx_Setup.exe`)**: Solid LZMA-compressed per-user installer (`%LOCALAPPDATA%\Programs\StreamerCalyx`) with zero UAC elevation, Start Menu/Desktop shortcuts, and Add/Remove Programs integration.
  - **Instant Sub-Second Boot (Hybrid Engine)**: Unpacked onedir execution eliminates PyInstaller's 2–3 second `%TEMP%` extraction latency.
  - **Standalone Portable (`StreamerCalyx_Portable.exe`)**: Single-file portable edition for flash drives and zero-install environments.
- **Antivirus Heuristic Hardening**:
  - Eliminated process startup `WH_KEYBOARD_LL` hooks, preventing behavioral scanner false positives (`IDP.HELU`).
  - Restored clean bytecode introspection (`optimize=0`) and removed command-line process-killing scripts.
- **Dual Authenticode EV Hardware Signing**:
  - All executables and installers are cryptographically signed with a DigiCert Extended Validation (EV) hardware token and RFC 3161 timestamps.
- **Per-Monitor V2 DPI Awareness & SLOBS Broadcast State Sync**:
  - Pixel-perfect edge-to-edge monitor border locking via explicit Win32 `SetWindowPos` coordinates.
  - Real-time RPC `streamingStatusChange` listener auto-resetting the "Go for Launch" mission control button when streams end in SLOBS.

---

### Phase 7.1: Production Maintenance, Tray Exit & Soundboard Thread Safety Hotfixes (`v3.0.1` / `v3.0.2`) — *Completed*
- **v3.0.1 Stable Hotfix**:
  - Fixed `NameError: name 'keyboard' is not defined` regression when closing the application from the Windows system tray context menu (`main.py`).
  - Added clean module-level import verification and fallback handling for the global keyboard hook dispatcher.
- **v3.0.2 Stable Hotfix**:
  - Fixed `RuntimeError: wrapped C/C++ object of type SoundboardLANServer has been deleted` during app exit.
  - Implemented thread-safe peer disconnect routines, atomic Qt signal unhooking, and graceful server socket shutdown before C++ Qt teardown (`soundboard_lan_bridge.py`, `director_tab.py`, `main.py`).
- **Release Ledger & Cryptographic Packaging**:
  - Compiled and published signed installers (`StreamerCalyx_Setup.exe` and `StreamerCalyx_Portable.exe`) to GitHub Release `v3.0.2`.
  - Registered releases in the standalone cryptographic ledger and encyclopedia (`C:\Users\thawi\Desktop\StreamerCalyx_Ledger.html`).

---

## 🚀 Version 4.0: The Modular Creator Ecosystem & Next-Gen Backstage Suite

Streamer Calyx V4 expands from a Twitch-centric live overlay and remote director into a comprehensive, multi-platform, modular streaming and content creation ecosystem.

---

### Phase 8: Core Shell & Navigation Redesign, Hotkey Sync Broker & Dynamic Scaling (`v4.0.0-alpha.1`) — *Completed*
*Regrouped sidebar categories, synchronized header dropdown, master audio tab, two-way hotkey broker, dynamic cross-monitor scaling, first-run wizard & context help.*

- **8.1 Left Sidebar Regrouping & Workflow-Based Reorganization**:
  - Re-group and re-order the left sidebar shell into logical, workflow-centered categories:
    - **MISSION CONTROL**:
      - 🚀 Launchpad (Page 0 — immediate top-level broadcast trigger)
      - 🏠 Main & Streaming Mode (Page 1 — core alert toggle & mode status)
    - **OVERLAY & VISUALS**:
      - 🎨 Alert Overlay Styles & Effects (monitor borders, animation triggers)
    - **AUDIO & SPEECH**:
      - 🔊 Soundboard & Audio Cues
      - 🎙️ Auto-Clip & Stream Markers
      - 🎧 Audio Devices & Routing (dedicated master view for WASAPI input/output device selection, gain trim, VoiceMeeter routing, and audio monitoring channels)
    - **STREAM TOOLS & AUTOMATION**:
      - 🟣 Twitch Channel & Macros
      - ⏱️ Chronos Timers
      - 📜 Rotating Text & Trivia Cycler
      - 🎬 Stream Director Panel
    - **SYSTEM & SETTINGS**:
      - 🖥️ Monitor Setup & Calibration (relocated from Overlay to System & Settings where hardware configuration belongs)
      - 🎮 Unified Hotkeys & Peripherals
      - ⚙️ System Diagnostics & Calibration
      - 📑 Logs & Debugging Suite
      - 🌸 About Streamer Calyx (Creator Socials & Tip deck)
- **8.2 Collapsible Sidebar Accordion & 1:1 Synchronized Collapsed Dropdown**:
  - Add collapsible accordion headers (`▼` / `▶`) to each category in the left sidebar to save vertical space.
  - **1:1 Dropdown Parity**: Update the header bar's collapsed view dropdown (`combo_collapsed_nav`) to dynamically mirror the exact category grouping, visual indentation, icons, and item order of the left sidebar so navigation is 100% identical whether the sidebar is expanded or collapsed.
- **8.3 Bi-Directional Hotkey Synchronization & Central Binding Broker**:
  - Establish a single-source-of-truth **Hotkey Broker**:
    - Any hotkey input widget across the app (Trivia manual advance, Chronos timer hotkeys, Alert manual triggers, Moment Bookmark hotkey, Auto-Clip test triggers, Soundboard quick buttons) is registered with the central hotkey broker.
    - All hotkeys are referenced, displayed, and editable within the **🎮 Hotkeys & Peripherals** tab.
    - **Two-Way Real-Time Sync**: Editing or clearing a hotkey on an individual tab immediately updates its row on the Hotkeys tab, and vice-versa.
    - Built-in conflict detection, duplicate prevention warnings, and synchronized persistence to `config.json`.
- **8.4 Dynamic Cross-Monitor Scaling & Multi-Ratio Resiliency**:
  - Multi-monitor responsive layout engine:
    - When the Calyx window is dragged between displays with differing scale factors (e.g. 100% 1080p, 125% 1440p, 150% 4K) or different aspect ratios (ultrawide 21:9, standard 16:9, portrait/vertical 9:16), the application listens to Win32 `WM_DPICHANGED` and Qt `screenChanged` events.
    - Dynamically recalculates widget sizes, margins, font scales, and scroll viewport constraints.
    - Guarantees zero widget clipping, no truncated text or action buttons, and automatic scrollbar engagement when vertical space is constrained on compact laptop or portrait monitors.
- **8.5 First-Run Interactive Setup Wizard**:
  - Launch a step-by-step onboarding wizard for first-time installs:
    - Welcome & Streamer vs. Content Creator Mode selection.
    - Automatic multi-monitor detection & DPI alignment check.
    - Default audio device selector (Microphone / VoiceMeeter Output B3).
    - 1-Click Streamlabs Desktop / OBS Studio WebSocket & Named Pipe handshake.
  - Add a **"Re-run Setup Wizard"** button in **System & Settings** for easy re-calibration anytime.
- **8.6 100% Comprehensive Tooltip Coverage & Context Help Cards**:
  - Add explanatory tooltips to **every** button, slider, checkbox, dropdown, and input field across all tabs.
  - **Context Help System**: Implement `Shift + Right-Click` on any UI element or section header to open an interactive **"What is this?"** floating help card containing detailed markdown explanations, hotkey tips, and usage recommendations.
- **8.7 Creator Socials & Support Deck in About Tab**:
  - Integrate official creator support and tip links into the **🌸 About** tab:
    - Direct **Streamlabs Tip** button (`https://streamlabs.com/thawizanator/tip`).
    - Direct **PayPal** donation link.
  - Full creator social media matrix with high-contrast clickable badges: Discord Community, Twitch Channel, YouTube Channel, and GitHub Repository.
- **8.8 Calyx Support Bot Telemetry & Diagnostic Schema (Beta / Early Access Readiness)**:
  - Standardize diagnostic export schemas and crash log formats (`debug.txt`, `crash.log`, `telemetry_report.json`) right from Day 1 of V4 development.
  - Guarantees that as soon as preview builds drop on the **Beta / Early Access** channel, testers' diagnostic bundles and bug reports are 100% ingestible and solvable by the standalone Calyx Support Bot.

---

### Phase 9: Content Creator & Offline Production Suite
*Empower offline video creators, YouTubers, and podcasters with dedicated session logging.*

- **9.1 Dual-Mode Operation (Streamer Mode vs. Content Creator Mode)**:
  - Add a dedicated **"Content Creator Mode"** checkbox alongside the existing "Streamer Mode" toggle.
  - Allows creators recording offline (without streaming to Twitch) to run Calyx's timers, soundboards, hotkeys, and marker logging without requiring Twitch authentication.
- **9.2 Offline Production Moments Logger**:
  - Real-time session logger writing formatted timestamped bookmarks to `%APPDATA%\StreamerCalyx\recording_moments.txt` and `.json`.
  - Captures elapsed recording time, system time, active window/game title, and event description for rapid video post-production.
- **9.3 Global Moment Bookmark Hotkey & Gamepad Chord**:
  - Register a dedicated global hotkey / controller button combo (e.g., `Guide + B` or configurable keyboard shortcut) to drop instant timestamped bookmarks during gameplay without pausing.
- **9.4 Stream Director Recording Control**:
  - Add a dedicated **"Start / Stop Recording"** button to the remote Stream Director dock.
  - Protect recording controls with a granular streamer security permission gate (`allow_recording_control`), preventing unauthorized co-host triggers.

---

### Phase 10: Native Acoustic Auto-Clip & Stream Marker System Overhaul
*Transition the validated DSP prosody engine from the standalone prototype into Calyx's core backend.*

- **10.1 Vectorized Acoustic Prosody DSP Pipeline (`auto_clip_engine.py`)**:
  - High-performance 20 Hz (50ms window) digital signal processing:
    - Stevens' power-law perceptual loudness expansion ($RMS^{0.5} + Peak^{0.5}$).
    - Sub-bass desk thump / mic drop rejection filter ($<70\text{ Hz}$).
    - Human vocal tract Voice Activity Detection ($80\text{ Hz} - 3500\text{ Hz}$).
    - Autocorrelation pitch tracking ($F_0$ 80–550 Hz) with sudden inflection detection ($>1.35\times$ baseline).
    - Human laughter envelope cadence tracking in the 4–6 Hz frequency window.
- **10.2 8-Zone Human Vocal Reaction Classifier**:
  - Automatically classifies every vocal spike into 8 distinct stream moments:
    1. 🔥 *Pure Hype Explosion*
    2. 😂 *Hysterical Laughter Fit*
    3. 😱 *High-Pitched Scream / Shriek*
    4. 📢 *Victory Shout / Callout*
    5. 😆 *Hyped Laughing Burst*
    6. 🗣️ *Intense Rapid Banter*
    7. 😮 *Loud Gasp / Shock*
    8. 💬 *Elevated Excitement*
- **10.3 Dual-Platform Dispatcher (Twitch Helix + OBS / SLOBS Replay Buffer)**:
  - Synchronously creates Twitch stream markers with customizable templates (`{icon} {tag} [{game}]`).
  - Triggers local instant video clipping via OBS Studio WebSocket (`SaveReplayBuffer`) or Streamlabs Desktop Named Pipe (`replayBufferService.save`).
  - 60-second anti-spam cooldown prevents disk flooding while continuing to log secondary peak reactions in the session history.
- **10.4 Dual-Tab Calibration GUI (`autoclip_tab.py`)**:
  - **Basic Tuning Tab**: Master hype threshold slider, min peak duration (100–800ms), anti-spam cooldown (15–120s), and scene whitelist.
  - **Advanced DSP Tab**: Voice Profiles (*Deep Voice*, *Mid/Conversational*, *High/Expressive*, *Dynamic Auto-Adapt*), Desk Thump filter aggressiveness, and 1-Click Game Genre Presets (*Default*, *😱 Horror*, *😂 Comedy*, *📢 FPS Shout*).
- **10.5 In-App Clip Vault & Highlight Browser**:
  - Replay folder watcher monitoring OBS/SLOBS replay directories.
  - Automatic timestamp-to-reaction video matching (e.g. `2026-11-15_21-40-48_😱_High-Pitched_Scream.mp4`).
  - Embedded lightweight preview player with timeline scrubber.
  - Video Editor Export Assistant: 1-click export of marker timestamps to YouTube descriptions and EDL / CSV timeline markers for DaVinci Resolve, Adobe Premiere Pro, and CapCut.

---

### Phase 11: Mission Control "De-Orbit" & Automated Stream Shutdown
*Execute seamless, professional broadcast sign-offs with one click.*

- **11.1 Automated De-Orbit Sequence**:
  - Add an automated **"De-Orbit / End Stream"** sequence to the Launchpad:
    1. Smoothly switch OBS / SLOBS to the designated **"Stream Ending / Outro"** or BRB scene.
    2. Automatically trigger the Stream Ending Credits / Text Scroller plugin.
    3. Start an on-screen visual countdown timer (e.g. 60 seconds).
    4. Mute open microphones to protect backstage privacy.
    5. Gracefully stop the broadcast stream in SLOBS / OBS when the countdown completes.
- **11.2 Safety Abort Window**:
  - Prominent red **"ABORT DE-ORBIT"** cancellation button available throughout the shutdown countdown to instantly halt the sequence if needed.

---

### Phase 12: Stream Director WAN/LAN Next-Gen Video Feed
*Provide remote directors and co-hosts with real-time visual situational awareness.*

- **12.1 Local LAN Low-Latency Video Stream**:
  - Direct local LAN video preview feed streamed from SLOBS / OBS virtual camera or RTSP/WebRTC stream directly into the Stream Director Panel.
- **12.2 Configurable Performance & FPS Throttle**:
  - User-configurable preview refresh rate slider (1 FPS, 5 FPS, 10 FPS, 15 FPS) to minimize CPU/GPU load on gaming rigs during intense gameplay.
- **12.3 Remote Recording Control Gate**:
  - Co-host dock button for starting/stopping OBS recording with live status indicators (`● REC [00:14:22]`).

---

### Phase 13: Multi-Platform Broadcast Gateway (YouTube Live & Kick)
*Expand Calyx's broadcast integrations beyond Twitch.*

- **13.1 YouTube Gaming / YouTube Live Integration**:
  - Secure Google OAuth2 authentication flow.
  - Live broadcast status watchdog & stream health monitoring.
  - Automatic stream marker creation via YouTube Live Streaming API.
- **13.2 Kick Streaming Target Compatibility**:
  - Kick channel metadata synchronization and webhook/API bridge.
- **13.3 Multi-Stream Unified Event Dispatcher**:
  - Unified dispatcher routing markers, titles, and category updates concurrently to Twitch, YouTube, and Kick based on active streaming destinations.

---

### Phase 14: Calyx Modular Plugin Architecture & Add-on Engine
*A modular ecosystem enabling creators to install, build, and share custom features.*

- **14.1 `.calyxplugin` Standard Package Format**:
  - Single-file compressed ZIP bundle containing:
    - `plugin.json` (Manifest: unique ID, name, version, author, category, requested permissions).
    - `main.py` (Plugin entry point inheriting from `CalyxPluginBase`).
    - Assets, icons, and bundled pure-Python modules.
- **14.2 1-Click Plugin Manager UI**:
  - Dedicated **🧩 Plugins & Add-ons** manager tab under System & Settings.
  - **Zero-Friction Installation**: Prominent "Install Plugin..." file dialog button + drag-and-drop `.calyxplugin` files directly into Calyx.
  - **Permission & Safety Review Modal**: Visual verification card detailing author, version, and requested permissions before mounting.
  - Toggle plugins on/off, inspect version updates, and 1-click uninstall.
- **14.3 Dynamic Sidebar & UI Injection**:
  - Plugins automatically inject their navigation button into the sidebar under their declared category (`STREAM TOOLS`, `OVERLAY & DISPLAY`, or dedicated `PLUGINS`).
  - Seamlessly injects plugin UI pages into `SettingsWindow`'s `QStackedWidget` with full Dark/Light theme inheritance.
- **14.4 Crash-Isolated `CalyxAPI` Runtime Engine**:
  - Protected API surface providing plugins access to:
    - Overlay notifications & banner toasts (`api.show_overlay_toast()`).
    - Config persistence in `%APPDATA%\StreamerCalyx\plugins\<plugin_id>\`.
    - Global hotkey & peripheral button listener hooks.
    - Twitch / YouTube / SLOBS event listeners.
  - Guarded error boundaries (`try/except` wrappers) preventing third-party plugin crashes from impacting core overlay or streaming hotkeys.
- **14.5 Launch & First-Party Core Plugins**:
  - **Stream Ending Credits**: Customizable rolling credits scroller (patrons, subscribers, mods, top gifters, and special thanks).
  - **Backstage Teleprompter**: Floating, resizable script prompter with adjustable scrolling speed and font size.
  - **Devo's Slots Mini-Game**: Interactive chat-driven or co-host casino slots mini-game.
  - **StreamElements & Streamlabs Web Bridge**: Direct event listener for web tips, merchandise alerts, and follower goals.
  - **Encrypted Backstage Peer Chat**: Low-latency, end-to-end encrypted direct text chat between the streamer and all connected remote directors during live sessions.
  - **VoiceMeeter / Discord Audio Ducking Hotkey**: Global push-to-duck hotkey temporarily attenuating Discord/game audio during intense stream callouts.
- **14.6 Developer Kit & 1-Click Exporter**:
  - In-app "Export as .calyxplugin" developer tool allowing developers to package folders into signed plugins with one click.
  - Complete starter documentation and example plugin templates.

---

### Phase 15: V4 Packaging, Dual EV Code Signing & Release Pipeline
*Enterprise-grade release packaging for production distribution.*

- **15.1 Optimized PyInstaller Build Pipeline (`main.spec`)**:
  - Bundle optimized `numpy`, `scipy.signal`, and `soundfile` dynamic libraries.
  - Exclude heavy unused Qt6 modules to maintain a lean binary footprint (~55–65 MB).
- **15.2 Dual-Distribution NSIS Modern Installer**:
  - **`StreamerCalyx_v4_Setup.exe`**: Solid LZMA-compressed per-user installer (`%LOCALAPPDATA%\Programs\StreamerCalyx`) with zero UAC elevation, Start Menu/Desktop shortcuts, and Add/Remove Programs integration.
  - **Instant Sub-Second Boot**: Unpacked onedir execution eliminating PyInstaller `%TEMP%` extraction delays.
  - **`StreamerCalyx_v4_Portable.exe`**: Standalone single-file portable edition.
- **15.3 Dual Authenticode EV Hardware Code Signing**:
  - Cryptographically sign all executables and installer packages using DigiCert Extended Validation (EV) hardware token with RFC 3161 timestamps.
  - Guarantee 100% false-positive-free antivirus ratings and zero Windows SmartScreen warnings.
- **15.4 Seamless Auto-Updater Integration**:
  - Background GitHub Releases version checks with automatic delta patching and safe restart.

---

## 🔮 Future Backlog (v5.0+ Horizon)

> [!NOTE]
> The following advanced capabilities are preserved in the long-term backlog for exploration following the Streamer Calyx V4 production cycle:

- **Mobile & Local Web Deck Companion**:
  - Lightweight local and remote web dashboard accessible from smartphones, tablets, or secondary browser tabs.
  - Touch buttons to trigger monitor alerts, Chronos timers, trivia cycler, and Stream Director commands without requiring external hardware like an Elgato Stream Deck.
- **Dedicated Browser Extension / Chrome Plugin**:
  - Custom browser extension packaged alongside Calyx.
  - Embed the Stream Director dock directly within Twitch/YouTube web pages, synchronize two-way communication between web chat and the desktop app, and provide automated stream viewport docking.
- **Automated Stream Health & Bitrate Drop Watchdog**:
  - Passive background monitor tracking dropped frames, encoder lags, and network bitrate fluctuations in OBS/SLOBS with subtle monitor border alert warnings.
- **Twitch Channel Points & Bits Event Bridge**:
  - Custom triggers binding Twitch Channel Points rewards and Bits events directly to soundboard audio cues, trivia reveals, or overlay animations.
- **Encrypted Cloud Sync for Multi-Rig Streamers**:
  - Secure end-to-end encrypted backup and synchronization of Calyx profiles, hotkeys, timers, and soundboard configs across dual-PC streaming setups.
