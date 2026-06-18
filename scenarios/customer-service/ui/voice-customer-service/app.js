/* ===== Voice AI Customer Service · Main Application =====
 *
 * 连接 TRTC Conversational AI 后端，实现：
 *   1. 点击 Start → get_config → TRTC 入房 → agent/start
 *   2. 左侧卡片 → 发送文本给 AI → TTS 回复
 *   3. Human Support → handoff/request → 排队动画 → 模拟接通
 *
 * TRTC 自定义消息协议（与 conversation-core 对齐）:
 *   发送 (client → bot):  cmdId=2, data 为 JSON 经 TextEncoder 编码的 ArrayBuffer
 *     type=20000 文本注入, type=20001 打断
 *   接收 (bot → client):  经 TextDecoder 解码 JSON
 *     type=10000 字幕(payload.text/end/roundid), type=10001 状态(payload.state)
 */
(function() {
  'use strict';

  // =====================================================================
  // STATE
  // =====================================================================
  var state = {
    active: false,
    healthy: false,
    mode: 'pre',           // pre / idle / listening / speaking / thinking
    sessionId: null,
    sdkAppId: 0,
    roomId: null,
    userId: null,
    userSig: null,
    agentUserId: null,
    trtcClient: null,
    micEnabled: false,
    handoffActive: false,
    queueTimer: null,
    queueSeconds: 0,
    localEchoes: [],       // [{ text, at: timestamp }] for dedup
    aiRoundText: {},       // roundid → accumulated text
    aiRoundLast: {},       // roundid → last chunk
    aiRoundBubbleId: {},   // roundid → DOM element id (not used in chat drawer)
    aiRoundBubbleEl: {},   // roundid → DOM element (bubble node in chat) for in-place update
    userBubbleOpen: false,
  };

  // Handoff keywords
  var HANDOFF_KEYWORDS = [
    'talk to agent', 'human agent', 'human support', 'real person',
    'live agent', 'speak to a human', 'transfer to agent', 'real human',
  ];
  var ECHO_TTL_MS = 30000;

  // =====================================================================
  // API helpers
  // =====================================================================
  function api(method, path, body) {
    var opts = { method: method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    return fetch(path, opts).then(function(resp) {
      return resp.json().then(function(data) {
        if (!resp.ok) {
          var msg = (data && (data.detail && data.detail.message || data.detail || data.msg)) || resp.statusText;
          throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
        }
        return data;
      });
    });
  }

  // =====================================================================
  // DOM helpers
  // =====================================================================
  function $(id) { return document.getElementById(id); }

  function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      var r = (Math.random() * 16) | 0;
      var v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  // =====================================================================
  // Connection status
  // =====================================================================
  function setConnected(on) {
    var dot = $('conn-dot');
    var txt = $('conn-text');
    var wrap = $('conn-status');
    if (!wrap) return;
    wrap.dataset.connected = on ? 'true' : 'false';
    if (on) {
      dot.style.background = '#34c77b';
      txt.textContent = 'Live · Connected';
    } else {
      dot.style.background = '#c9c2d8';
      txt.textContent = 'Disconnected';
    }
  }

  // =====================================================================
  // Mode / visual state
  // =====================================================================
  function setMode(m) {
    state.mode = m;
    var orb = document.querySelector('.orb-wrap');
    var wave = $('wave');
    var aiState = $('ai-state');
    var aiSub = $('ai-substate');

    if (orb) {
      orb.classList.remove('idle', 'listening', 'speaking');
    }
    if (wave) {
      wave.classList.remove('idle', 'listening', 'speaking');
    }

    switch (m) {
      case 'pre':
        if (orb) orb.classList.add('idle');
        if (wave) wave.classList.add('idle');
        if (aiState) aiState.textContent = 'Ready to start conversation';
        if (aiSub) aiSub.innerHTML = 'Press <span class="kbd">Start</span> below to begin a real-time voice session';
        break;
      case 'idle':
        if (orb) orb.classList.add('idle');
        if (wave) wave.classList.add('idle');
        if (aiState) aiState.textContent = 'Listening for you';
        if (aiSub) aiSub.textContent = 'Speak naturally · I will respond in real time';
        break;
      case 'listening':
        if (orb) orb.classList.add('listening');
        if (wave) wave.classList.add('listening');
        if (aiState) aiState.textContent = 'Listening\u2026';
        if (aiSub) aiSub.textContent = 'Capturing your voice';
        break;
      case 'thinking':
        if (orb) orb.classList.add('listening');
        if (wave) wave.classList.add('listening');
        if (aiState) aiState.textContent = 'Thinking\u2026';
        if (aiSub) aiSub.textContent = 'Processing your request';
        break;
      case 'speaking':
        if (orb) orb.classList.add('speaking');
        if (wave) wave.classList.add('speaking');
        if (aiState) aiState.textContent = 'AI is speaking\u2026';
        if (aiSub) aiSub.textContent = 'Streaming response over TRTC';
        break;
    }
  }

  // =====================================================================
  // Chat drawer bubbles
  // =====================================================================
  function openDrawer() {
    $('im-drawer').classList.add('open');
  }

  function addBubble(role, text) {
    var chat = $('chat');
    var div;
    if (role === 'system') {
      div = document.createElement('div');
      div.className = 'flex justify-center';
      div.innerHTML = '<div class="bubble system">' + escapeHtml(text) + '</div>';
      chat.appendChild(div);
    } else {
      var row = document.createElement('div');
      row.className = 'bubble-row ' + role;
      var avatar = role === 'ai'
        ? '<div class="bubble-avatar ai">AI</div>'
        : '<div class="bubble-avatar user">U</div>';
      var inner = '<div class="bubble ' + role + '">' + escapeHtml(text) + '</div>';
      row.innerHTML = role === 'user' ? inner + avatar : avatar + inner;
      chat.appendChild(row);
    }
    chat.scrollTop = chat.scrollHeight;
  }

  function addTyping() {
    var chat = $('chat');
    var row = document.createElement('div');
    row.className = 'bubble-row ai';
    row.id = 'typing-row';
    row.innerHTML = '<div class="bubble-avatar ai">AI</div><div class="bubble ai"><div class="typing"><span></span><span></span><span></span></div></div>';
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
  }

  function removeTyping() {
    var r = $('typing-row');
    if (r) r.remove();
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // =====================================================================
  // Local echo dedup
  // =====================================================================
  function pushLocalEcho(text) {
    var now = Date.now();
    state.localEchoes = state.localEchoes.filter(function(e) { return now - e.at < ECHO_TTL_MS; });
    state.localEchoes.push({ text: (text || '').trim(), at: now });
  }

  function consumeLocalEcho(text) {
    var tt = (text || '').trim();
    if (!tt) return false;
    var now = Date.now();
    state.localEchoes = state.localEchoes.filter(function(e) { return now - e.at < ECHO_TTL_MS; });
    for (var i = 0; i < state.localEchoes.length; i++) {
      var e = state.localEchoes[i];
      var a = e.text.toLowerCase();
      var b = tt.toLowerCase();
      if (e.text === tt || a.indexOf(b) !== -1 || b.indexOf(a) !== -1) {
        state.localEchoes.splice(i, 1);
        return true;
      }
    }
    return false;
  }

  // =====================================================================
  // TRTC custom message: send (binary-encoded JSON)
  // =====================================================================
  function sendCustomToAgent(message) {
    if (!state.trtcClient) return false;
    try {
      state.trtcClient.sendCustomMessage({
        cmdId: 2,
        data: new TextEncoder().encode(JSON.stringify(message)).buffer,
      });
      return true;
    } catch (e) {
      console.warn('sendCustomMessage failed', e);
      return false;
    }
  }

  function sendInterrupt() {
    return sendCustomToAgent({
      type: 20001,
      sender: state.userId,
      receiver: [state.agentUserId],
      payload: { id: uuid(), timestamp: Date.now() },
    });
  }

  // =====================================================================
  // TRTC custom message: receive handler
  // =====================================================================
  function handleCustomMessage(event) {
    var txt;
    try {
      txt = new TextDecoder().decode(event.data);
    } catch (e) {
      console.warn('decode custom msg failed', e);
      return;
    }
    var data;
    try {
      data = JSON.parse(txt);
    } catch (e) {
      console.warn('parse custom msg failed', e);
      return;
    }

    if (!data || typeof data !== 'object') return;

    // type=10001: AI state change (payload.state)
    if (data.type === 10001) {
      var code = data.payload && data.payload.state;
      switch (code) {
        case 1: setMode('listening'); break;
        case 2: setMode('thinking'); break;
        case 3: setMode('speaking'); break;
        case 4: setMode('idle'); break;
        default: break;
      }
      return;
    }

    // type=10000: subtitle / caption
    if (data.type !== 10000) return;

    var payload = data.payload || {};
    var text = payload.text || '';
    var end = payload.end === true;
    var roundid = payload.roundid || '';
    var sender = data.sender || event.userId || '';
    var isUser = sender === state.userId;

    if (isUser) {
      // User utterance echoed back by bot
      if (end && text.trim()) {
        var tt = text.trim();
        if (consumeLocalEcho(tt)) return;  // dedup
        if (!state.userBubbleOpen) {
          addBubble('user', tt);
          state.userBubbleOpen = true;
        }
        onUserUtteranceFinal(tt);
        setTimeout(function() { state.userBubbleOpen = false; }, 1500);
      }
      return;
    }

    // AI caption: incremental, aggregated by roundid — update a SINGLE bubble
    if (text.trim() && roundid) {
      removeTyping();
      var last = state.aiRoundLast[roundid] || '';
      var cur = state.aiRoundText[roundid] || '';
      var isAccumulative = last && text.indexOf(last) === 0;
      state.aiRoundText[roundid] = isAccumulative ? text : (cur + text);
      state.aiRoundLast[roundid] = text;

      // Update existing bubble or create a new one for this round
      var existingEl = state.aiRoundBubbleEl[roundid];
      if (existingEl && existingEl.parentNode) {
        // In-place update of the existing bubble text
        existingEl.textContent = state.aiRoundText[roundid];
      } else {
        // First chunk of a new round: create a new bubble and track it
        var row = document.createElement('div');
        row.className = 'bubble-row ai';
        row.innerHTML = '<div class="bubble-avatar ai">AI</div><div class="bubble ai">' + escapeHtml(state.aiRoundText[roundid]) + '</div>';
        var chat = $('chat');
        chat.appendChild(row);
        chat.scrollTop = chat.scrollHeight;
        // Track the inner .bubble element (not the row) for text updates
        state.aiRoundBubbleEl[roundid] = row.querySelector('.bubble.ai');
      }
    }

    if (end && roundid) {
      delete state.aiRoundText[roundid];
      delete state.aiRoundLast[roundid];
      delete state.aiRoundBubbleEl[roundid];
    }
  }

  // =====================================================================
  // Start: get_config → TRTC enterRoom → agent/start
  // =====================================================================
  function start() {
    if (state.active) return;

    setMode('thinking');
    addBubble('system', 'Initializing connection\u2026');
    $('btn-start').disabled = true;

    api('POST', '/api/v1/get_config', {})
      .then(function(cfg) {
        // Response is wrapped: { code, msg, data: { session_id, sdk_app_id, ... } }
        var d = cfg.data || cfg;
        state.sessionId = d.session_id;
        state.sdkAppId = d.sdk_app_id;
        state.roomId = parseInt(d.room_id, 10);
        state.userId = d.user_id;
        state.userSig = d.user_sig;
        state.agentUserId = d.agent_user_id;

        console.log('[start] config:', JSON.stringify({
          sessionId: state.sessionId,
          sdkAppId: state.sdkAppId,
          roomId: state.roomId,
          userId: state.userId,
          agentUserId: state.agentUserId,
        }));

        if (typeof TRTC === 'undefined') throw new Error('TRTC Web SDK not loaded');

        state.trtcClient = TRTC.create();
        state.trtcClient.on(TRTC.EVENT.CUSTOM_MESSAGE, handleCustomMessage);
        state.trtcClient.on(TRTC.EVENT.ERROR, function(err) {
          console.error('[trtc] error', err);
          addBubble('system', 'TRTC error. Please try restarting.');
        });

        return state.trtcClient.enterRoom({
          roomId: state.roomId,
          scene: 'rtc',
          sdkAppId: state.sdkAppId,
          userId: state.userId,
          userSig: state.userSig,
        });
      })
      .then(function() {
        // Start local audio — unmuted to capture user voice
        return state.trtcClient.startLocalAudio().then(function() {
          state.micEnabled = true;
          updateMicUI();
        }).catch(function(e) {
          console.warn('mic init failed (continuing in text-only mode):', e);
          state.micEnabled = false;
        });
      })
      .then(function() {
        return api('POST', '/api/v1/agent/start', {
          session_id: state.sessionId,
          language: 'en',
        });
      })
      .then(function() {
        state.active = true;
        setConnected(true);

        // Expand dock
        var dock = $('dock');
        if (dock) dock.dataset.state = 'expanded';

        // Show Open chat button
        var chatBtn = $('ctl-chat');
        if (chatBtn) chatBtn.style.display = 'inline-flex';

        setMode('idle');
        addBubble('system', 'Connected. Click the microphone to talk, or type below.');
        if (window.AppData && window.AppData.greeting) {
          addBubble('ai', window.AppData.greeting);
        }
      })
      .catch(function(err) {
        console.error('[start] error', err);
        addBubble('system', 'Failed to connect: ' + (err.message || err));
        setMode('pre');
        setConnected(false);
        $('btn-start').disabled = false;
        safeExitRoom();
      });
  }

  // =====================================================================
  // Hangup
  // =====================================================================
  function safeExitRoom() {
    var p = Promise.resolve();
    if (state.trtcClient) {
      p = state.trtcClient.exitRoom().catch(function() {}).then(function() {
        if (state.trtcClient) { state.trtcClient.destroy(); state.trtcClient = null; }
      });
    }
    return p;
  }

  function hangupCleanup() {
    if (state.queueTimer) {
      clearInterval(state.queueTimer);
      state.queueTimer = null;
    }
    stopQueueAnimation();
    state.active = false;
    state.handoffActive = false;
    state.sessionId = null;
    state.localEchoes = [];
    state.aiRoundText = {};
    state.aiRoundLast = {};
    state.aiRoundBubbleId = {};
    state.aiRoundBubbleEl = {};

    var dock = $('dock');
    if (dock) dock.dataset.state = 'collapsed';
    var chatBtn = $('ctl-chat');
    if (chatBtn) chatBtn.style.display = 'none';
    $('btn-start').disabled = false;

    if (state.micEnabled) {
      state.micEnabled = false;
      updateMicUI();
    }
  }

  function hangup() {
    addBubble('system', 'Ending session\u2026');

    var stopPromise = Promise.resolve();
    if (state.sessionId) {
      stopPromise = api('POST', '/api/v1/agent/stop', { session_id: state.sessionId }).catch(function() {});
    }

    stopPromise.then(function() {
      return safeExitRoom();
    }).then(function() {
      setConnected(false);
      hangupCleanup();
      addBubble('system', 'Conversation ended.');
      setMode('pre');
      closeDetailViewSilent();
    });
  }

  // =====================================================================
  // Send text to AI
  // =====================================================================
  function sendText(text) {
    text = (text || '').trim();
    if (!text) return;

    openDrawer();
    if (!state.active || !state.trtcClient) {
      addBubble('system', 'Please start the conversation first.');
      return;
    }

    // During handoff flow, block user messages from reaching LLM
    if (state.handoffActive) {
      addBubble('system', 'Please wait while we connect you to an agent.');
      return;
    }

    addBubble('user', text);
    pushLocalEcho(text);
    sendInterrupt();

    setTimeout(function() {
      sendCustomToAgent({
        type: 20000,
        sender: state.userId,
        receiver: [state.agentUserId],
        payload: { id: uuid(), message: text, timestamp: Date.now() },
      });
    }, 120);

    onUserUtteranceFinal(text);
  }

  function onUserUtteranceFinal(text) {
    // During handoff, block all user input from LLM + TTS processing
    if (state.handoffActive) return;

    var lower = text.toLowerCase();
    if (HANDOFF_KEYWORDS.some(function(kw) { return lower.indexOf(kw) !== -1; })) {
      talkToAgent();
      return;
    }
    // KB lookup silently
    silentKbLookup(text).catch(function(e) { console.debug('[kb] error', e); });
  }

  function silentKbLookup(query) {
    return api('POST', '/api/v1/kb/search', { query: query, top_k: 1 })
      .then(function(resp) {
        var hits = resp && resp.data ? resp.data : (Array.isArray(resp) ? resp : []);
        if (!hits.length) return;
        var top = hits[0];
        if (typeof top.score === 'number' && top.score < 0.15) return;
        console.debug('[kb hit]', top.entry && top.entry.id, 'score=', top.score);
      });
  }

  // =====================================================================
  // Mic toggle
  // =====================================================================
  function updateMicUI() {
    var btn = $('btn-mic');
    var btnD = $('btn-mic-detail');
    [btn, btnD].forEach(function(b) {
      if (!b) return;
      b.classList.toggle('muted', !state.micEnabled);
      b.innerHTML = '<i data-lucide="' + (state.micEnabled ? 'mic' : 'mic-off') + '" class="w-5 h-5"></i>';
    });
    if (window.lucide) lucide.createIcons();
  }

  function toggleMute() {
    if (!state.trtcClient) return;
    state.micEnabled = !state.micEnabled;
    state.trtcClient.updateLocalAudio({ mute: !state.micEnabled }).catch(function(e) {
      console.error('toggleMic failed', e);
      state.micEnabled = !state.micEnabled;
    });
    updateMicUI();
    if (state.micEnabled) sendInterrupt();
  }

  // =====================================================================
  // Human support (handoff)
  // =====================================================================
  function talkToAgent() {
    if (!state.active || !state.sessionId) {
      addBubble('system', 'Please start the conversation before requesting an agent.');
      return;
    }
    if (state.handoffActive) {
      addBubble('system', 'You are already in the handoff queue. Please wait.');
      return;
    }

    state.handoffActive = true;

    addBubble('system', 'Transferring to a human agent\u2026');
    setMode('speaking');

    // Call handoff API
    api('POST', '/api/v1/handoff/request', { session_id: state.sessionId }).catch(function() {});

    // Show queue animation
    startQueueAnimation();

    // Step 1: TTS voice guidance — connecting to human agent
    setTimeout(function() {
      if (!state.handoffActive) return;
      var voiceText = "Connecting you to a live agent. Please hold on momentarily.";
      pushLocalEcho(voiceText);
      addBubble('ai', voiceText);
      sendInterrupt();
      setTimeout(function() {
        sendCustomToAgent({
          type: 20000,
          sender: state.userId,
          receiver: [state.agentUserId],
          payload: { id: uuid(), message: voiceText, timestamp: Date.now() },
        });
      }, 120);
      setMode('idle');
    }, 600);

    // Step 2: TTS waiting queue progress
    setTimeout(function() {
      if (!state.handoffActive) return;
      var waitText = "Still waiting in the queue. Your estimated wait time is about 30 seconds. Thank you for your patience.";
      pushLocalEcho(waitText);
      addBubble('ai', waitText);
      sendInterrupt();
      setTimeout(function() {
        sendCustomToAgent({
          type: 20000,
          sender: state.userId,
          receiver: [state.agentUserId],
          payload: { id: uuid(), message: waitText, timestamp: Date.now() },
        });
      }, 120);
    }, 4500);

    // Step 3: Simulate agent connection after 8 seconds
    setTimeout(function() {
      if (!state.handoffActive) return;
      stopQueueAnimation();

      api('POST', '/api/v1/handoff/connect', { session_id: state.sessionId }).catch(function() {});

      var connectText = "A human agent has joined the conversation. How can we help you today?";
      // Register local echo so the agent's subtitle replay won't re-trigger talkToAgent
      pushLocalEcho(connectText);
      addBubble('system', 'Agent connected');
      addBubble('ai', connectText);
      sendInterrupt();
      setTimeout(function() {
        sendCustomToAgent({
          type: 20000,
          sender: state.userId,
          receiver: [state.agentUserId],
          payload: { id: uuid(), message: connectText, timestamp: Date.now() },
        });
      }, 120);
      setMode('speaking');
      setTimeout(function() { setMode('idle'); }, 3000);

      // Flow complete — return to normal conversation
      state.handoffActive = false;
    }, 8000);
  }

  function startQueueAnimation() {
    var wrap = $('queue-progress-wrap');
    var wave = $('wave');
    var bar = $('queue-bar');
    var timer = $('queue-timer');
    if (!wrap) return;

    // Hide wave visualizer, show progress bar in its place
    if (wave) wave.style.display = 'none';
    wrap.classList.add('show-progress');

    // Reset bar to 0% and trigger 0→100% transition once
    if (bar) {
      bar.style.transition = 'none';
      bar.style.width = '0%';
      // Force reflow, then start the 8s linear fill
      void bar.offsetWidth;
      bar.style.transition = 'width 8000ms linear';
      bar.style.width = '100%';
    }

    state.queueSeconds = 0;
    if (timer) timer.textContent = '0:00';

    // Timer ticks — counters only, don't touch the bar
    state.queueTimer = setInterval(function() {
      state.queueSeconds++;
      var t = $('queue-timer');
      if (t) {
        var m = Math.floor(state.queueSeconds / 60);
        var s = state.queueSeconds % 60;
        t.textContent = m + ':' + (s < 10 ? '0' : '') + s;
      }
      if (state.queueSeconds >= 8 && state.queueTimer) {
        clearInterval(state.queueTimer);
        state.queueTimer = null;
      }
    }, 1000);
  }

  function stopQueueAnimation() {
    if (state.queueTimer) {
      clearInterval(state.queueTimer);
      state.queueTimer = null;
    }
    var wrap = $('queue-progress-wrap');
    if (wrap) wrap.classList.remove('show-progress');

    // Restore wave
    var wave = $('wave');
    if (wave) wave.style.display = '';
  }

  // =====================================================================
  // Detail view (product / order cards)
  // =====================================================================
  function ratingStars(r) {
    r = Math.round(r);
    return '\u2605'.repeat(r) + '\u2606'.repeat(5 - r);
  }

  function showProductDetail(p) {
    var desc = 'Premium ' + p.name.toLowerCase() + ' crafted with breathable mesh upper, responsive cushioning and durable rubber outsole. Perfect for everyday wear and athletic performance.';
    $('detail-question').textContent = 'Would you like to know more about the ' + p.name + '?';
    $('detail-card').innerHTML =
      '<div class="dc-product">' +
        '<img class="pic" src="' + p.img + '" alt="' + escapeHtml(p.name) + '"/>' +
        '<div class="info">' +
          '<div class="pname">' + escapeHtml(p.name) + '</div>' +
          '<div class="rating"><span class="stars">' + ratingStars(4.6) + '</span><span>4.6 (2.4k reviews)</span></div>' +
          '<div class="desc">' + desc + '</div>' +
          '<div class="row">' +
            '<div class="price">$' + p.price + '<span class="cur">USD</span></div>' +
            '<button class="add" title="Add to cart"><i data-lucide="plus" class="w-4 h-4"></i></button>' +
          '</div>' +
        '</div>' +
      '</div>';
    openDetailView();

    // Send product context to AI with full details (system-level injection — no user bubble)
    var contextMsg = '[system] The customer is viewing product "' + p.name + '" (ID: ' + p.id + '), priced at $' + p.price + ', tagged as "' + p.tag + '". ' + desc + ' The customer wants to know more about this product. Please provide a helpful, detailed response including key features, price, and purchase recommendation.';
    sendInterrupt();
    setTimeout(function() {
      sendCustomToAgent({
        type: 20000,
        sender: state.userId,
        receiver: [state.agentUserId],
        payload: { id: uuid(), message: contextMsg, timestamp: Date.now() },
      });
    }, 120);
  }

  function showOrderDetail(o) {
    var p = window.AppData.products[o.pidx];
    var total = (p.price * o.qty).toFixed(2);
    $('detail-question').textContent = 'Here are the details for order #' + o.id + '. Need any help with it?';
    $('detail-card').innerHTML =
      '<div class="dc-order">' +
        '<div class="ohead">' +
          '<div>' +
            '<div class="oid">Order #' + o.id + '</div>' +
            '<div class="odate">Placed on ' + o.date + '</div>' +
          '</div>' +
          '<span class="badge ' + o.cls + '">' + o.status + '</span>' +
        '</div>' +
        '<div class="obody">' +
          '<img src="' + p.img + '" alt="' + escapeHtml(p.name) + '"/>' +
          '<div class="flex-1 min-w-0">' +
            '<div class="pn">' + escapeHtml(p.name) + '</div>' +
            '<div class="pq">$' + p.price + ' \u00d7 ' + o.qty + '</div>' +
          '</div>' +
        '</div>' +
        '<div class="ototal">' +
          '<span class="lbl">Order total</span>' +
          '<span class="val">$' + total + ' <span style="font-size:11px;color:var(--muted);font-weight:600">USD</span></span>' +
        '</div>' +
      '</div>';
    openDetailView();

    // Send order context to AI with full details (system-level injection — no user bubble)
    var contextMsg = '[system] The customer is viewing order #' + o.id + ', placed on ' + o.date + '. ' +
      'Product: ' + p.name + ' (ID: ' + p.id + '), ' + o.qty + 'x at $' + p.price + ' each, order total $' + total + '. ' +
      'Status: ' + o.status + '. The customer wants to inquire about this order. ' +
      'Please provide a helpful response about the order status, shipping details, and any relevant next steps.';
    sendInterrupt();
    setTimeout(function() {
      sendCustomToAgent({
        type: 20000,
        sender: state.userId,
        receiver: [state.agentUserId],
        payload: { id: uuid(), message: contextMsg, timestamp: Date.now() },
      });
    }, 120);
  }

  function openDetailView() {
    var rc = $('right-console');
    if (rc) rc.dataset.view = 'detail';
    $('im-drawer').classList.remove('open');
    $('dock-detail').style.display = 'flex';
    $('dock').style.display = 'none';
    if (window.lucide) lucide.createIcons();
  }

  function closeDetailView() {
    var rc = $('right-console');
    if (rc) rc.dataset.view = 'default';
    $('dock-detail').style.display = 'none';
    $('dock').style.display = 'flex';
  }

  function closeDetailViewSilent() {
    var rc = $('right-console');
    if (rc && rc.dataset.view === 'detail') {
      rc.dataset.view = 'default';
      $('dock-detail').style.display = 'none';
      $('dock').style.display = 'flex';
    }
  }

  // =====================================================================
  // Toast
  // =====================================================================
  var toastTimer = null;
  function showToast(msg) {
    var t = $('kb-toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function() { t.classList.remove('show'); }, 2600);
  }

  // =====================================================================
  // Render product & order lists
  // =====================================================================
  function renderProducts(filter) {
    var box = $('tab-products');
    if (!box) return;
    box.innerHTML = '';
    var q = (filter || '').trim().toLowerCase();
    window.AppData.products
      .filter(function(p) { return !q || p.name.toLowerCase().indexOf(q) !== -1; })
      .forEach(function(p) {
        var el = document.createElement('div');
        el.className = 'product-card';
        el.innerHTML =
          '<img class="product-thumb-img" src="' + p.img + '" alt="' + escapeHtml(p.name) + '" loading="lazy"/>' +
          '<div class="flex-1 min-w-0">' +
            '<div class="name truncate">' + escapeHtml(p.name) + '</div>' +
            '<div class="meta">' +
              '<span class="price">$' + p.price + '</span>' +
              '<span class="tag ' + p.tagCls + '">' + p.tag + '</span>' +
            '</div>' +
          '</div>' +
          '<i data-lucide="chevron-right" class="w-4 h-4 text-muted flex-shrink-0"></i>';
        el.addEventListener('click', function() {
          if (!state.active) {
            showToast('Please press Start to connect AI before viewing product details.');
            return;
          }
          showProductDetail(p);
        });
        box.appendChild(el);
      });
    if (window.lucide) lucide.createIcons();
  }

  function renderOrders(filter) {
    var box = $('tab-orders');
    if (!box) return;
    box.innerHTML = '';
    var q = (filter || '').trim().toLowerCase();
    window.AppData.orders
      .filter(function(o) {
        var p = window.AppData.products[o.pidx];
        return !q || o.id.indexOf(q) !== -1 || (p && p.name.toLowerCase().indexOf(q) !== -1) || o.status.toLowerCase().indexOf(q) !== -1;
      })
      .forEach(function(o) {
        var p = window.AppData.products[o.pidx];
        var el = document.createElement('div');
        el.className = 'order-card';
        el.innerHTML =
          '<div class="top">' +
            '<div>' +
              '<div class="oid">Order #' + o.id + '</div>' +
              '<div class="odate">' + o.date + '</div>' +
            '</div>' +
            '<span class="badge ' + o.cls + '">' + o.status + '</span>' +
          '</div>' +
          '<div class="body">' +
            '<img src="' + p.img + '" alt="' + escapeHtml(p.name) + '"/>' +
            '<div class="min-w-0 flex-1">' +
              '<div class="pname truncate">' + escapeHtml(p.name) + '</div>' +
              '<div class="pprice">$' + p.price + ' \u00d7 ' + o.qty + '</div>' +
            '</div>' +
          '</div>';
        el.addEventListener('click', function() {
          if (!state.active) {
            showToast('Please press Start to connect AI before viewing order details.');
            return;
          }
          showOrderDetail(o);
        });
        box.appendChild(el);
      });
  }

  // =====================================================================
  // Health check
  // =====================================================================
  function checkHealth() {
    api('GET', '/api/v1/health')
      .then(function(h) {
        var allOk = h.status === 'ok';
        state.healthy = allOk;
        if (!h.configured) {
          addBubble('system', 'Credentials missing: ' + (h.missing || []).join(', '));
        }
        console.log('Backend healthy:', allOk, h.checks);
      })
      .catch(function(err) {
        console.error('[health] error', err);
        state.healthy = false;
      });
  }

  // =====================================================================
  // INIT
  // =====================================================================
  function init() {
    // Render data
    if (!window.AppData) {
      console.warn('AppData not loaded, using fallback');
      window.AppData = { products: [], orders: [], greeting: 'Hello! How can I help you?' };
    }
    renderProducts();
    renderOrders();

    // Health check
    checkHealth();

    // Dock buttons
    $('btn-start').addEventListener('click', function() { start(); });
    $('btn-mic').addEventListener('click', function() { toggleMute(); });
    $('btn-agent').addEventListener('click', function() { talkToAgent(); });
    $('btn-hang').addEventListener('click', function() { hangup(); });

    // Detail view dock buttons
    $('btn-mic-detail').addEventListener('click', function() { toggleMute(); });
    $('btn-agent-detail').addEventListener('click', function() { talkToAgent(); });
    $('btn-hang-detail').addEventListener('click', function() {
      hangup();
      closeDetailViewSilent();
    });

    // Compact back button
    $('compact-back').addEventListener('click', function() { closeDetailView(); });

    // Chat controls
    $('ctl-chat').addEventListener('click', function() { openDrawer(); });
    $('im-close').addEventListener('click', function() {
      $('im-drawer').classList.remove('open');
    });

    // Chat input
    var input = $('chat-input');
    var sendBtn = $('send-btn');
    var submit = function() {
      var v = input.value;
      input.value = '';
      sendText(v);
    };
    sendBtn.addEventListener('click', submit);
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') submit();
    });

    // KB Tabs
    document.querySelectorAll('.kb-tab').forEach(function(t) {
      t.addEventListener('click', function() {
        document.querySelectorAll('.kb-tab').forEach(function(x) { x.classList.remove('active'); });
        t.classList.add('active');
        var tab = t.dataset.tab;
        $('tab-products').classList.toggle('hidden', tab !== 'products');
        $('tab-orders').classList.toggle('hidden', tab !== 'orders');
      });
    });

    // Search
    $('kb-search').addEventListener('input', function(e) {
      var v = e.target.value;
      var tab = document.querySelector('.kb-tab.active').dataset.tab;
      if (tab === 'products') renderProducts(v);
      else renderOrders(v);
    });

    // Initial state
    setMode('pre');
    if (window.lucide) lucide.createIcons();
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose for external use
  window.VoiceAI = {
    start: start,
    hangup: hangup,
    toggleMute: toggleMute,
    talkToAgent: talkToAgent,
    sendText: sendText,
    isActive: function() { return state.active; },
  };
})();
