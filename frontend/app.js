/**
 * CareVoice AI - Modern Minimalist Browser Voice Client
 * Matches exact minimalist reference aesthetic:
 * 3D Robot Visualizer, Call Status Indicators, Live Timer,
 * Retell-style Tool Calls, and 24kHz Jitter-Buffered Deepgram Aura-2 Playback.
 */

// DOM Elements
const mainCallBtn = document.getElementById('main-call-btn');
const micToggleBtn = document.getElementById('mic-toggle-btn');
const optionsBtn = document.getElementById('options-btn');
const optionsModal = document.getElementById('options-modal');
const closeOptionsBtn = document.getElementById('close-options-btn');
const clearTranscriptBtn = document.getElementById('clear-transcript-btn');

// Status & Indicators
const callStatusDot = document.getElementById('call-status-dot');
const callStatusLabel = document.getElementById('call-status-label');
const callTimerTop = document.getElementById('call-timer-top');
const callTimerTranscript = document.getElementById('call-timer-transcript');
const callCaptionTitle = document.getElementById('call-caption-title');
const callCaptionDesc = document.getElementById('call-caption-desc');
const subStatusDot = document.getElementById('sub-status-dot');
const recordingPill = document.getElementById('recording-pill');
const recLabel = document.getElementById('rec-label');
const speakerPulse = document.getElementById('speaker-pulse');

// Transcript & Error
const transcriptContainer = document.getElementById('transcript-container');
const partialContainer = document.getElementById('partial-container');
const partialText = document.getElementById('partial-text');
const errorBanner = document.getElementById('error-banner');
const errorMessage = document.getElementById('error-message');
const dismissErrorBtn = document.getElementById('dismiss-error-btn');

// Compatibility DOM references (for background events if any)
const legacyStartCallBtn = document.getElementById('start-call-btn');
const legacyEndCallBtn = document.getElementById('end-call-btn');
const connectionIndicator = document.getElementById('connection-indicator');
const connectionStatusText = document.getElementById('connection-status-text');
const micDot = document.getElementById('mic-dot');
const micStatusText = document.getElementById('mic-status-text');
const speakerDot = document.getElementById('speaker-dot');
const speakerStatusText = document.getElementById('speaker-status-text');
const turnBadge = document.getElementById('turn-badge');

// Audio and WebSocket state
let audioCtx = null;
let micStream = null;
let scriptProcessor = null;
let sourceNode = null;
let muteGain = null;
let socket = null;
let isCallActive = false;
let isMicMuted = false;

// Call Duration Timer
let callStartTime = null;
let callTimerInterval = null;

function startCallTimer() {
  callStartTime = Date.now();
  updateTimerUI();
  if (callTimerInterval) clearInterval(callTimerInterval);
  callTimerInterval = setInterval(updateTimerUI, 1000);
}

function stopCallTimer() {
  if (callTimerInterval) {
    clearInterval(callTimerInterval);
    callTimerInterval = null;
  }
  callStartTime = null;
  document.querySelectorAll('.call-timer-display').forEach((el) => {
    el.textContent = '00:00';
  });
}

function updateTimerUI() {
  if (!callStartTime) return;
  const elapsed = Math.floor((Date.now() - callStartTime) / 1000);
  const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const seconds = String(elapsed % 60).padStart(2, '0');
  const timeStr = `${minutes}:${seconds}`;
  document.querySelectorAll('.call-timer-display').forEach((el) => {
    el.textContent = timeStr;
  });
}

function getFormattedCallTimestamp() {
  if (!callStartTime) return '00:00';
  const elapsed = Math.floor((Date.now() - callStartTime) / 1000);
  const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const seconds = String(elapsed % 60).padStart(2, '0');
  return `${minutes}:${seconds}`;
}

// -------------------------------------------------------------
// Resilient Jitter-Buffered PCM Audio Stream Player (24kHz)
// Eliminates syllable cuts, buffering underruns, and stuttering.
// -------------------------------------------------------------
class PcmStreamPlayer {
  constructor(sampleRate = 24000) {
    this.sampleRate = sampleRate;
    this.audioCtx = null;
    this.audioQueue = []; // Array of Float32Array chunks
    this.totalQueuedDuration = 0;
    this.isPlaying = false;
    this.isBuffering = true;
    this.nextStartTime = 0;
    this.activeSources = [];
    this.onSpeakingChange = null;
    this.BUFFER_THRESHOLD_SEC = 0.25; // 250ms pre-buffer cushion to prevent network micro-stutter
  }

  setAudioContext(ctx) {
    this.audioCtx = ctx;
  }

  feedPcmChunk(base64Audio) {
    if (!this.audioCtx || !base64Audio) return;

    try {
      const binaryStr = atob(base64Audio);
      const len = binaryStr.length;
      const alignedLen = len - (len % 2);
      if (alignedLen === 0) return;

      const bytes = new Uint8Array(alignedLen);
      for (let i = 0; i < alignedLen; i++) {
        bytes[i] = binaryStr.charCodeAt(i);
      }

      const int16 = new Int16Array(bytes.buffer);
      const float32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768.0;
      }

      const chunkDuration = float32.length / this.sampleRate;
      this.audioQueue.push({ float32, duration: chunkDuration });
      this.totalQueuedDuration += chunkDuration;

      this.processQueue();
    } catch (err) {
      console.error('[PCM Player Decode Error]', err);
    }
  }

  processQueue() {
    if (!this.audioCtx) return;
    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }

    // Initial buffering cushion: wait until we have at least BUFFER_THRESHOLD_SEC (250ms)
    // before starting the playback clock. This guarantees continuous, uninterrupted audio.
    if (this.isBuffering) {
      if (this.totalQueuedDuration < this.BUFFER_THRESHOLD_SEC) {
        return; // Keep buffering
      }
      this.isBuffering = false;
      this.nextStartTime = this.audioCtx.currentTime + 0.05;
    }

    // Schedule all buffered chunks contiguously with sample-accurate Web Audio timing
    while (this.audioQueue.length > 0) {
      const item = this.audioQueue.shift();
      this.totalQueuedDuration -= item.duration;

      const audioBuffer = this.audioCtx.createBuffer(1, item.float32.length, this.sampleRate);
      audioBuffer.copyToChannel(item.float32, 0);

      const source = this.audioCtx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.audioCtx.destination);

      const currentTime = this.audioCtx.currentTime;
      if (this.nextStartTime < currentTime) {
        // If an underrun occurred, resync smoothly
        this.nextStartTime = currentTime + 0.02;
      }

      source.start(this.nextStartTime);
      this.nextStartTime += item.duration;
      this.activeSources.push(source);

      if (!this.isPlaying) {
        this.isPlaying = true;
        if (this.onSpeakingChange) this.onSpeakingChange(true);
      }

      source.onended = () => {
        const idx = this.activeSources.indexOf(source);
        if (idx !== -1) {
          this.activeSources.splice(idx, 1);
        }
        if (this.activeSources.length === 0 && this.audioQueue.length === 0) {
          this.isPlaying = false;
          this.isBuffering = true;
          this.nextStartTime = 0;
          if (this.onSpeakingChange) this.onSpeakingChange(false);
        }
      };
    }
  }

  stopAll() {
    this.audioQueue = [];
    this.totalQueuedDuration = 0;
    this.isBuffering = true;
    this.nextStartTime = 0;
    this.activeSources.forEach((src) => {
      try {
        src.stop();
      } catch (e) {}
    });
    this.activeSources = [];
    if (this.isPlaying) {
      this.isPlaying = false;
      if (this.onSpeakingChange) this.onSpeakingChange(false);
    }
  }
}

const pcmPlayer = new PcmStreamPlayer(24000);
pcmPlayer.onSpeakingChange = (speaking) => {
  updateSpeakerStatus(speaking);
};

// Error banner handlers
function showError(msg) {
  if (errorMessage && errorBanner) {
    errorMessage.textContent = msg;
    errorBanner.style.display = 'flex';
  }
}

function clearError() {
  if (errorBanner) errorBanner.style.display = 'none';
  if (errorMessage) errorMessage.textContent = '';
}

if (dismissErrorBtn) dismissErrorBtn.addEventListener('click', clearError);

// Status update helpers
function updateConnectionStatus(status) {
  if (connectionIndicator) connectionIndicator.className = 'status-indicator ' + status;
  if (status === 'connected') {
    if (connectionStatusText) connectionStatusText.textContent = 'Connected';
    if (turnBadge) turnBadge.textContent = 'Listening';
    if (callStatusDot) callStatusDot.classList.add('active');
    if (subStatusDot) subStatusDot.classList.add('active');
    if (callStatusLabel) callStatusLabel.textContent = 'Live Call';
    if (callCaptionTitle) callCaptionTitle.textContent = 'Call in progress';
    if (callCaptionDesc) callCaptionDesc.textContent = 'Listening and transcribing...';
    if (recordingPill) recordingPill.classList.add('active');
    if (recLabel) recLabel.textContent = 'Recording...';
  } else if (status === 'connecting') {
    if (connectionStatusText) connectionStatusText.textContent = 'Connecting...';
    if (turnBadge) turnBadge.textContent = 'Connecting';
    if (callStatusLabel) callStatusLabel.textContent = 'Connecting...';
    if (callCaptionTitle) callCaptionTitle.textContent = 'Connecting to Sophia...';
    if (callCaptionDesc) callCaptionDesc.textContent = 'Establishing secure WebSocket session...';
  } else {
    if (connectionStatusText) connectionStatusText.textContent = 'Disconnected';
    if (turnBadge) turnBadge.textContent = 'Offline';
    if (callStatusDot) callStatusDot.classList.remove('active');
    if (subStatusDot) subStatusDot.classList.remove('active');
    if (callStatusLabel) callStatusLabel.textContent = 'Ready to Call';
    if (callCaptionTitle) callCaptionTitle.textContent = 'Ready to Call';
    if (callCaptionDesc) callCaptionDesc.textContent = 'Click the call button to connect with Sophia';
    if (recordingPill) recordingPill.classList.remove('active');
    if (recLabel) recLabel.textContent = 'Idle';
  }
}

function updateMicStatus(active) {
  if (active) {
    if (micDot) {
      micDot.className = 'status-dot dot-active';
      micStatusText.textContent = 'Mic: Live';
    }
    if (micToggleBtn) {
      micToggleBtn.classList.add('mic-active');
      micToggleBtn.classList.remove('mic-muted');
    }
  } else {
    if (micDot) {
      micDot.className = 'status-dot dot-inactive';
      micStatusText.textContent = 'Mic: Off';
    }
    if (micToggleBtn) {
      micToggleBtn.classList.remove('mic-active');
      micToggleBtn.classList.remove('mic-speaking');
    }
  }
}

let micLevelTimeout = null;
function updateMicLevel(peak) {
  if (!isCallActive || isMicMuted) return;
  if (peak > 0.03) {
    if (micDot) {
      micDot.className = 'status-dot dot-speaking';
      micStatusText.textContent = 'Mic: Speaking 🎙️';
    }
    if (micToggleBtn) {
      micToggleBtn.classList.add('mic-speaking');
    }
    clearTimeout(micLevelTimeout);
    micLevelTimeout = setTimeout(() => {
      if (isCallActive) {
        if (micDot) {
          micDot.className = 'status-dot dot-active';
          micStatusText.textContent = 'Mic: Live';
        }
        if (micToggleBtn) {
          micToggleBtn.classList.remove('mic-speaking');
        }
      }
    }, 450);
  }
}

function updateSpeakerStatus(speaking) {
  if (speaking) {
    if (speakerDot) {
      speakerDot.className = 'status-dot dot-speaking';
      speakerStatusText.textContent = 'Sophia: Speaking';
    }
    if (speakerPulse) speakerPulse.classList.add('speaking');
    if (turnBadge) turnBadge.textContent = 'Sophia Speaking';
    if (isCallActive) {
      if (callCaptionTitle) callCaptionTitle.textContent = 'Sophia Speaking';
      if (callCaptionDesc) callCaptionDesc.textContent = 'Streaming voice response...';
    }
  } else {
    if (speakerDot) {
      speakerDot.className = 'status-dot dot-inactive';
      speakerStatusText.textContent = 'Sophia: Idle';
    }
    if (speakerPulse) speakerPulse.classList.remove('speaking');
    if (isCallActive) {
      if (turnBadge) turnBadge.textContent = 'Listening';
      if (callCaptionTitle) callCaptionTitle.textContent = 'Call in progress';
      if (callCaptionDesc) callCaptionDesc.textContent = 'Listening and transcribing...';
    }
  }
}

// Transcript UI Helpers (Matching reference image)
let currentAssistantBubble = null;
let currentAssistantText = '';

function handleAssistantTextStart() {
  const welcome = document.getElementById('welcome-msg');
  if (welcome) welcome.remove();

  // Create message wrapper matching user reference screenshot
  const wrapper = document.createElement('div');
  wrapper.className = 'msg-wrapper assistant';

  // Metadata Row
  const meta = document.createElement('div');
  meta.className = 'msg-meta';

  const authorInfo = document.createElement('div');
  authorInfo.className = 'msg-author-info';

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar ai-avatar';
  avatar.textContent = '✦';

  const name = document.createElement('span');
  name.className = 'msg-author-name';
  name.textContent = 'AI';

  authorInfo.appendChild(avatar);
  authorInfo.appendChild(name);

  const timestamp = document.createElement('span');
  timestamp.className = 'msg-timestamp';
  timestamp.textContent = getFormattedCallTimestamp();

  meta.appendChild(authorInfo);
  meta.appendChild(timestamp);

  // Bubble
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble assistant-bubble';
  bubble.textContent = '';

  wrapper.appendChild(meta);
  wrapper.appendChild(bubble);
  transcriptContainer.appendChild(wrapper);

  currentAssistantBubble = bubble;
  currentAssistantText = '';

  transcriptContainer.scrollTop = transcriptContainer.scrollHeight;
}

function handleAssistantTextDelta(delta) {
  if (!currentAssistantBubble) {
    handleAssistantTextStart();
  }
  currentAssistantText += delta;
  currentAssistantBubble.textContent = currentAssistantText;
  transcriptContainer.scrollTop = transcriptContainer.scrollHeight;
}

function handleAssistantTextEnd() {
  currentAssistantBubble = null;
  currentAssistantText = '';
}

function escapeHtml(str) {
  if (typeof str !== 'string') return str;
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatToolDisplayName(toolName) {
  if (!toolName) return 'Tool Execution';
  return toolName.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function toggleToolDrawer(drawerId, chevronId) {
  const drawer = document.getElementById(drawerId);
  const chevron = document.getElementById(chevronId);
  if (!drawer) return;
  const isCurrentlyHidden = drawer.style.display === 'none';
  drawer.style.display = isCurrentlyHidden ? 'block' : 'none';
  if (chevron) {
    chevron.textContent = isCurrentlyHidden ? '∨' : '›';
    chevron.classList.toggle('open', isCurrentlyHidden);
  }
  if (transcriptContainer) {
    transcriptContainer.scrollTop = transcriptContainer.scrollHeight;
  }
}

if (typeof window !== 'undefined') {
  window.toggleToolDrawer = toggleToolDrawer;
}

function handleToolCallStart(toolName, toolCallId, args) {
  const welcome = document.getElementById('welcome-msg');
  if (welcome) welcome.remove();

  handleAssistantTextEnd();

  const elementId = `tool-start-${toolCallId || ('id_' + Math.random().toString(36).slice(2, 8))}`;
  const drawerId = `drawer-${elementId}`;
  const chevronId = `chevron-${elementId}`;

  // Prevent duplicate rendering of same tool call start
  if (document.getElementById(elementId)) return;

  const wrapper = document.createElement('div');
  wrapper.className = 'retell-tool-event tool-call-start';
  wrapper.id = elementId;

  const cleanName = escapeHtml(toolName || 'clinic_tool');
  const safeId = escapeHtml(toolCallId || 'call_start');
  const argsFormatted = escapeHtml(typeof args === 'string' ? args : JSON.stringify(args || {}, null, 2));

  wrapper.innerHTML = `
    <div class="retell-tool-header" onclick="toggleToolDrawer('${drawerId}', '${chevronId}')" title="Click to view tool arguments">
      <span class="retell-wrench-icon">🔧</span>
      <span class="retell-tool-text">Called <span class="tool-name-code">${cleanName}</span></span>
      <span class="retell-chevron" id="${chevronId}">›</span>
    </div>
    <div class="retell-tool-drawer" id="${drawerId}" style="display: none;">
      <div class="retell-field"><span class="retell-field-label">tool_call_id:</span> <span class="retell-field-val">${safeId}</span></div>
      <div class="retell-field"><span class="retell-field-label">arguments:</span></div>
      <pre class="retell-code-box">${argsFormatted}</pre>
    </div>
  `;

  transcriptContainer.appendChild(wrapper);
  transcriptContainer.scrollTop = transcriptContainer.scrollHeight;
}

function handleToolCallResult(toolName, toolCallId, result, isSuccess) {
  const welcome = document.getElementById('welcome-msg');
  if (welcome) welcome.remove();

  handleAssistantTextEnd();

  const elementId = `tool-result-${toolCallId || ('id_' + Math.random().toString(36).slice(2, 8))}`;
  const drawerId = `drawer-${elementId}`;
  const chevronId = `chevron-${elementId}`;

  // Prevent duplicate rendering of same tool call result
  if (document.getElementById(elementId)) return;

  const wrapper = document.createElement('div');
  wrapper.className = `retell-tool-event ${isSuccess ? 'tool-call-success' : 'tool-call-fail'}`;
  wrapper.id = elementId;

  const safeId = escapeHtml(toolCallId || 'call_result');
  const resultFormatted = escapeHtml(typeof result === 'string' ? result : JSON.stringify(result || {}, null, 2));
  const wrenchClass = isSuccess ? 'wrench-success' : 'wrench-fail';
  const textClass = isSuccess ? 'text-success' : 'text-fail';
  const statusLabel = isSuccess ? 'Tool call succeeded' : 'Tool call failed';

  wrapper.innerHTML = `
    <div class="retell-tool-header" onclick="toggleToolDrawer('${drawerId}', '${chevronId}')" title="Click to expand/collapse tool response">
      <span class="retell-wrench-icon ${wrenchClass}">🔧</span>
      <span class="retell-tool-text ${textClass}">${statusLabel}</span>
      <span class="retell-chevron open" id="${chevronId}">∨</span>
    </div>
    <div class="retell-tool-drawer" id="${drawerId}" style="display: block;">
      <div class="retell-field"><span class="retell-field-label">tool_call_id:</span> <span class="retell-field-val">${safeId}</span></div>
      <div class="retell-field"><span class="retell-field-label">${isSuccess ? 'response:' : 'error:'}</span></div>
      <pre class="retell-code-box">${resultFormatted}</pre>
    </div>
  `;

  transcriptContainer.appendChild(wrapper);
  transcriptContainer.scrollTop = transcriptContainer.scrollHeight;
}

function appendMessage(role, text) {
  const welcome = document.getElementById('welcome-msg');
  if (welcome) welcome.remove();

  const wrapper = document.createElement('div');
  wrapper.className = `msg-wrapper ${role}`;

  const meta = document.createElement('div');
  meta.className = role === 'user' ? 'msg-meta user-meta' : 'msg-meta';

  const timestamp = document.createElement('span');
  timestamp.className = 'msg-timestamp';
  timestamp.textContent = getFormattedCallTimestamp();

  const authorInfo = document.createElement('div');
  authorInfo.className = 'msg-author-info';

  const name = document.createElement('span');
  name.className = 'msg-author-name';
  name.textContent = role === 'user' ? 'You' : 'AI';

  const avatar = document.createElement('div');
  avatar.className = role === 'user' ? 'msg-avatar user-avatar' : 'msg-avatar ai-avatar';
  avatar.textContent = role === 'user' ? '👤' : '✦';

  if (role === 'user') {
    authorInfo.appendChild(name);
    authorInfo.appendChild(avatar);
    meta.appendChild(timestamp);
    meta.appendChild(authorInfo);
  } else {
    authorInfo.appendChild(avatar);
    authorInfo.appendChild(name);
    meta.appendChild(authorInfo);
    meta.appendChild(timestamp);
  }

  const bubble = document.createElement('div');
  bubble.className = role === 'user' ? 'msg-bubble user-bubble' : 'msg-bubble assistant-bubble';
  bubble.textContent = text;

  wrapper.appendChild(meta);
  wrapper.appendChild(bubble);
  transcriptContainer.appendChild(wrapper);

  transcriptContainer.scrollTop = transcriptContainer.scrollHeight;
}

function updatePartialTranscript(text) {
  if (!text || !text.trim()) {
    if (partialContainer) partialContainer.style.display = 'none';
    if (partialText) partialText.textContent = '';
  } else {
    if (partialContainer) partialContainer.style.display = 'flex';
    if (partialText) partialText.textContent = text;
  }
}

// Downsampler: Converts native browser Float32 audio to 16,000 Hz 16-bit linear PCM
function downsampleTo16k(inputBuffer, inputSampleRate) {
  if (inputSampleRate === 16000) {
    const output = new Int16Array(inputBuffer.length);
    for (let i = 0; i < inputBuffer.length; i++) {
      const s = Math.max(-1, Math.min(1, inputBuffer[i]));
      output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return output.buffer;
  }

  const ratio = inputSampleRate / 16000;
  const newLength = Math.round(inputBuffer.length / ratio);
  const result = new Int16Array(newLength);

  let offsetResult = 0;
  let offsetInput = 0;

  while (offsetResult < result.length) {
    const nextOffsetInput = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetInput; i < nextOffsetInput && i < inputBuffer.length; i++) {
      accum += inputBuffer[i];
      count++;
    }
    const avg = count > 0 ? accum / count : 0;
    const s = Math.max(-1, Math.min(1, avg));
    result[offsetResult] = s < 0 ? s * 0x8000 : s * 0x7fff;
    offsetResult++;
    offsetInput = nextOffsetInput;
  }

  return result.buffer;
}

// Playback: Routes 24kHz 16-bit linear PCM into resilient jitter-buffered player
function playPcm24kChunk(base64Audio) {
  pcmPlayer.feedPcmChunk(base64Audio);
}

// Stop all currently playing audio immediately (barge-in / interruption)
function stopAllPlayback() {
  pcmPlayer.stopAll();
}

// Start Call Logic
async function startCall() {
  clearError();
  updateConnectionStatus('connecting');
  
  if (mainCallBtn) {
    mainCallBtn.disabled = true;
    mainCallBtn.title = 'Connecting...';
  }

  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    try {
      audioCtx = new AudioContextClass({ sampleRate: 24000 });
    } catch (e) {
      audioCtx = new AudioContextClass();
    }
    pcmPlayer.setAudioContext(audioCtx);
    if (audioCtx.state === 'suspended') {
      await audioCtx.resume();
    }

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/api/ws/voice`;
    socket = new WebSocket(wsUrl);
    socket.binaryType = 'arraybuffer';

    socket.onopen = () => {
      console.log('✅ WebSocket connected to CareVoice AI backend');
      isCallActive = true;
      startCallTimer();
      updateConnectionStatus('connected');
      updateMicStatus(true);

      if (mainCallBtn) {
        mainCallBtn.disabled = false;
        mainCallBtn.classList.remove('call-idle');
        mainCallBtn.classList.add('call-active');
        mainCallBtn.title = 'End Call';
      }

      sourceNode = audioCtx.createMediaStreamSource(micStream);
      scriptProcessor = audioCtx.createScriptProcessor(2048, 1, 1);
      muteGain = audioCtx.createGain();
      muteGain.gain.value = 0;

      scriptProcessor.onaudioprocess = (e) => {
        if (!isCallActive || isMicMuted) return;

        const inputChannelData = e.inputBuffer.getChannelData(0);

        let peak = 0;
        for (let i = 0; i < inputChannelData.length; i++) {
          const absVal = Math.abs(inputChannelData[i]);
          if (absVal > peak) peak = absVal;
        }
        updateMicLevel(peak);

        const pcm16Buffer = downsampleTo16k(inputChannelData, audioCtx.sampleRate);
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(pcm16Buffer);
        }
      };

      sourceNode.connect(scriptProcessor);
      scriptProcessor.connect(muteGain);
      muteGain.connect(audioCtx.destination);
    };

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type !== 'assistant_audio') {
          console.log('📨 [WS Message]', msg.type, msg);
        }

        if (msg.type === 'user_transcript') {
          if (!msg.final) {
            updatePartialTranscript(msg.text);
          } else {
            updatePartialTranscript('');
            appendMessage('user', msg.text);
          }
        } else if (msg.type === 'assistant_text_start') {
          handleAssistantTextStart();
        } else if (msg.type === 'assistant_text_delta') {
          handleAssistantTextDelta(msg.text);
        } else if (msg.type === 'assistant_text_end') {
          handleAssistantTextEnd();
        } else if (msg.type === 'assistant_text') {
          if (currentAssistantBubble) {
            currentAssistantBubble.textContent = msg.text;
            handleAssistantTextEnd();
          } else {
            appendMessage('assistant', msg.text);
          }
        } else if (msg.type === 'tool_call_start') {
          handleToolCallStart(msg.tool_name, msg.tool_call_id, msg.arguments);
        } else if (msg.type === 'tool_call_result') {
          handleToolCallResult(msg.tool_name, msg.tool_call_id, msg.result, msg.success);
        } else if (msg.type === 'assistant_audio') {
          playPcm24kChunk(msg.audio);
        } else if (msg.type === 'interrupted') {
          console.log('🛑 Caller interrupted Sophia; stopping audio playback.');
          stopAllPlayback();
          handleAssistantTextEnd();
        } else if (msg.type === 'error') {
          showError(msg.message || 'An error occurred in the voice pipeline.');
          handleAssistantTextEnd();
        }
      } catch (err) {
        console.error('Error handling WebSocket message:', err);
      }
    };

    socket.onerror = (err) => {
      console.error('WebSocket error:', err);
      showError('WebSocket connection error. Is backend running on port 8000?');
      endCall();
    };

    socket.onclose = () => {
      console.log('🔌 WebSocket disconnected');
      endCall();
    };

  } catch (err) {
    console.error('Start call failed:', err);
    showError('Could not start call: ' + (err.message || err.name));
    endCall();
  }
}

// End Call Logic
function endCall() {
  isCallActive = false;
  stopCallTimer();

  stopAllPlayback();
  handleAssistantTextEnd();
  updatePartialTranscript('');
  updateMicStatus(false);
  updateSpeakerStatus(false);
  updateConnectionStatus('disconnected');

  if (mainCallBtn) {
    mainCallBtn.disabled = false;
    mainCallBtn.classList.remove('call-active');
    mainCallBtn.classList.add('call-idle');
    mainCallBtn.title = 'Start Call';
  }

  if (scriptProcessor && sourceNode) {
    try {
      sourceNode.disconnect();
      scriptProcessor.disconnect();
      if (muteGain) muteGain.disconnect();
    } catch (e) {}
    scriptProcessor = null;
    sourceNode = null;
    muteGain = null;
  }

  if (micStream) {
    try {
      micStream.getTracks().forEach((track) => track.stop());
    } catch (e) {}
    micStream = null;
  }

  if (audioCtx) {
    try {
      audioCtx.close();
    } catch (e) {}
    audioCtx = null;
  }

  if (socket) {
    try {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'stop' }));
        socket.close();
      }
    } catch (e) {}
    socket = null;
  }
}

// Toggle Mic Mute
function toggleMicMute() {
  if (!isCallActive) return;
  isMicMuted = !isMicMuted;
  if (isMicMuted) {
    if (micToggleBtn) {
      micToggleBtn.classList.remove('mic-active');
      micToggleBtn.classList.add('mic-muted');
      micToggleBtn.title = 'Microphone Muted (Click to Unmute)';
    }
  } else {
    if (micToggleBtn) {
      micToggleBtn.classList.add('mic-active');
      micToggleBtn.classList.remove('mic-muted');
      micToggleBtn.title = 'Microphone Live (Click to Mute)';
    }
  }
}

// Event Listeners
if (mainCallBtn) {
  mainCallBtn.addEventListener('click', () => {
    if (isCallActive) {
      endCall();
    } else {
      startCall();
    }
  });
}

if (micToggleBtn) {
  micToggleBtn.addEventListener('click', toggleMicMute);
}

// Options Modal Listeners
if (optionsBtn && optionsModal) {
  optionsBtn.addEventListener('click', () => {
    optionsModal.style.display = 'flex';
  });
}

if (closeOptionsBtn && optionsModal) {
  closeOptionsBtn.addEventListener('click', () => {
    optionsModal.style.display = 'none';
  });
}

if (clearTranscriptBtn && transcriptContainer) {
  clearTranscriptBtn.addEventListener('click', () => {
    transcriptContainer.innerHTML = `
      <div class="transcript-system-msg" id="welcome-msg">
        <div class="clinic-intro-card">
          <h3>Absolute Dental Las Vegas</h3>
          <p>Transcript cleared. Click the call button on the left to speak with Sophia.</p>
        </div>
      </div>
    `;
    if (optionsModal) optionsModal.style.display = 'none';
  });
}

// Close modal if user clicks outside of modal content
window.addEventListener('click', (e) => {
  if (optionsModal && e.target === optionsModal) {
    optionsModal.style.display = 'none';
  }
});
