import os
import sys
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Ensure root directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

# Import the core FastAPI app from api.py
from api import app as api_app

app = api_app

# Modern, responsive single-page Web UI served on Vercel at root '/'
HTML_UI = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ Ollama Beam:Cloud AI & Tracker Console (Vercel)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
    </style>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen flex flex-col">
    <!-- Top Navbar -->
    <header class="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
        <div class="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <span class="text-2xl">⚡</span>
                <div>
                    <h1 class="font-bold text-lg text-slate-900 leading-tight">Beam:Cloud AI & REST Tracker</h1>
                    <p class="text-xs text-slate-500">Hosted on Vercel • Neon PostgreSQL • Ollama Cloud</p>
                </div>
            </div>
            <div class="flex items-center space-x-2">
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 border border-emerald-200">
                    🟢 Neon DB
                </span>
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 border border-blue-200">
                    ☁️ Vercel Serverless
                </span>
                <a href="/docs" target="_blank" class="text-xs font-semibold text-blue-600 hover:text-blue-800 bg-blue-50 px-3 py-1 rounded border border-blue-200 transition">
                    Swagger API Docs ↗
                </a>
            </div>
        </div>
        <!-- Navigation Tabs -->
        <nav class="max-w-7xl mx-auto px-4 flex space-x-6 border-t border-slate-100 text-sm font-medium">
            <button onclick="switchTab('chat')" id="tab-btn-chat" class="py-2.5 border-b-2 border-blue-600 text-blue-600 font-semibold transition">💬 AI Agent Chat</button>
            <button onclick="switchTab('config')" id="tab-btn-config" class="py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 transition">⚡ REST API & Tracker Config</button>
            <button onclick="switchTab('guardrail')" id="tab-btn-guardrail" class="py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 transition">🛡️ Guardrails & Kill-Switch</button>
            <button onclick="switchTab('logs')" id="tab-btn-logs" class="py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 transition">📊 AI Tracking Logs</button>
        </nav>
    </header>

    <!-- Main Container -->
    <main class="max-w-7xl mx-auto px-4 py-6 flex-1 w-full">
        <!-- TAB 1: CHAT -->
        <section id="tab-chat" class="tab-content active space-y-4">
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 flex flex-col h-[650px]">
                <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between bg-slate-50 rounded-t-xl">
                    <div class="flex items-center space-x-2">
                        <span class="font-semibold text-sm text-slate-700">Chat with Ollama beam:cloud</span>
                        <span id="active-model-tag" class="text-xs bg-slate-200 text-slate-700 px-2 py-0.5 rounded">beam:cloud</span>
                    </div>
                    <div class="flex items-center space-x-3">
                        <input id="agent-name-input" type="text" value="Beam-Agent" class="text-xs border border-slate-300 rounded px-2 py-1 w-36" placeholder="Agent Name">
                        <button onclick="clearChat()" class="text-xs text-slate-500 hover:text-red-600 transition">Clear Chat</button>
                    </div>
                </div>
                
                <!-- Chat Message Area -->
                <div id="chat-messages" class="flex-1 overflow-y-auto p-5 space-y-4">
                    <div class="flex items-start space-x-3">
                        <div class="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-xs shrink-0">AI</div>
                        <div class="bg-slate-100 rounded-lg p-3 text-sm max-w-2xl text-slate-800">
                            Hello! I am your AI agent powered by <b>Ollama beam:cloud</b> running serverless on Vercel. Ask me anything or test the tracking REST API!
                        </div>
                    </div>
                </div>

                <!-- Chat Input Form -->
                <div class="p-4 border-t border-slate-200 bg-white rounded-b-xl">
                    <form onsubmit="sendMessage(event)" class="flex space-x-2">
                        <input id="user-input" type="text" placeholder="Type instructions or questions for the AI agent..." class="flex-1 border border-slate-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" required>
                        <button type="submit" id="send-btn" class="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-semibold hover:bg-blue-700 transition flex items-center space-x-1 shrink-0">
                            <span>Send</span>
                            <span>🚀</span>
                        </button>
                    </form>
                </div>
            </div>
        </section>

        <!-- TAB 2: REST API & TRACKER CONFIGURATION -->
        <section id="tab-config" class="tab-content space-y-6">
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-6">
                <div class="flex items-center justify-between border-b border-slate-100 pb-4">
                    <div>
                        <h2 class="text-lg font-bold text-slate-900">⚡ Dynamic REST API & Tracker Configuration</h2>
                        <p class="text-xs text-slate-500">Stored and persisted directly in Neon PostgreSQL. Updates take effect immediately.</p>
                    </div>
                    <button onclick="autoGenerateConfig()" class="bg-emerald-600 text-white text-xs font-semibold px-3 py-2 rounded-lg hover:bg-emerald-700 transition shadow-sm">
                        ⚡ Auto-Generate New Key & Profile
                    </button>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-semibold text-slate-700 mb-1">REST API Connection Name</label>
                        <input id="cfg-name" type="text" class="w-full text-sm border border-slate-300 rounded-lg px-3 py-2">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-700 mb-1">External API Base URL</label>
                        <input id="cfg-url" type="text" class="w-full text-sm border border-slate-300 rounded-lg px-3 py-2">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-700 mb-1">API Key Header Name</label>
                        <input id="cfg-header" type="text" value="x-api-key" class="w-full text-sm border border-slate-300 rounded-lg px-3 py-2">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-700 mb-1">API Key / Token (Secret)</label>
                        <div class="flex space-x-2">
                            <input id="cfg-token" type="text" class="flex-1 text-sm border border-slate-300 rounded-lg px-3 py-2 font-mono text-xs">
                            <button onclick="generateRandomToken()" type="button" class="bg-slate-200 text-slate-700 text-xs px-3 py-2 rounded-lg hover:bg-slate-300">🔑 New</button>
                        </div>
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-700 mb-1">Target Model</label>
                        <input id="cfg-model" type="text" value="beam:cloud" class="w-full text-sm border border-slate-300 rounded-lg px-3 py-2">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-700 mb-1">Upstream Ollama Cloud Endpoint</label>
                        <input id="cfg-ollama-url" type="text" value="https://ollama.com/api/chat" class="w-full text-sm border border-slate-300 rounded-lg px-3 py-2">
                    </div>
                </div>

                <div class="flex items-center space-x-3 pt-2">
                    <button onclick="saveConfiguration()" class="bg-blue-600 text-white text-sm font-semibold px-5 py-2.5 rounded-lg hover:bg-blue-700 transition shadow">
                        💾 Save to Neon PostgreSQL & Activate
                    </button>
                    <button onclick="pingHealth()" class="bg-slate-100 text-slate-700 text-sm font-medium px-4 py-2.5 rounded-lg hover:bg-slate-200 border border-slate-300">
                        🧪 Test Connection Health
                    </button>
                </div>
                <div id="cfg-alert" class="hidden text-xs p-3 rounded-lg font-medium"></div>
            </div>
        </section>

        <!-- TAB 3: GUARDRAILS & KILL-SWITCH -->
        <section id="tab-guardrail" class="tab-content space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <!-- Kill Switch Card -->
                <div class="bg-white rounded-xl shadow-sm border border-red-200 p-6 space-y-4 md:col-span-1">
                    <div class="flex items-center space-x-2">
                        <span class="text-xl">🛑</span>
                        <h3 class="font-bold text-red-700 text-base">Emergency Kill-Switch</h3>
                    </div>
                    <p class="text-xs text-slate-500">Stop an in-flight agent immediately via REST API before it returns any wrong or harmful result.</p>
                    
                    <div>
                        <label class="block text-xs font-semibold text-slate-700 mb-1">Session ID to Abort</label>
                        <input id="kill-session-id" type="text" class="w-full text-xs border border-slate-300 rounded px-2.5 py-1.5" placeholder="Current Session ID">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-700 mb-1">Reason</label>
                        <input id="kill-reason" type="text" value="User triggered emergency kill-switch" class="w-full text-xs border border-slate-300 rounded px-2.5 py-1.5">
                    </div>
                    <button onclick="triggerKillSwitch()" class="w-full bg-red-600 hover:bg-red-700 text-white text-xs font-bold py-2.5 rounded-lg transition shadow-sm">
                        🛑 STOP & ABORT AGENT NOW
                    </button>
                    <div id="kill-result" class="hidden text-xs p-2.5 rounded border"></div>
                </div>

                <!-- Rules List -->
                <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4 md:col-span-2">
                    <div class="flex items-center justify-between border-b border-slate-100 pb-3">
                        <div>
                            <h3 class="font-bold text-slate-900 text-base">🛡️ Configured Pre-Delivery Guardrails</h3>
                            <p class="text-xs text-slate-500">Scans responses & reasoning traces before reaching user.</p>
                        </div>
                        <button onclick="loadGuardrails()" class="text-xs text-blue-600 hover:underline">🔄 Refresh</button>
                    </div>
                    <div id="guardrails-list" class="space-y-2 text-xs">
                        <p class="text-slate-400">Loading rules from Neon DB...</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- TAB 4: TRACKING LOGS -->
        <section id="tab-logs" class="tab-content space-y-6">
            <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
                <div class="flex items-center justify-between border-b border-slate-100 pb-4">
                    <div>
                        <h2 class="text-lg font-bold text-slate-900">📊 Live AI Tracking Logs (Neon PostgreSQL)</h2>
                        <p class="text-xs text-slate-500">Every request, prompt, response, latency, and token metric tracked in real-time.</p>
                    </div>
                    <button onclick="loadLogs()" class="bg-slate-100 text-slate-700 text-xs font-semibold px-3 py-1.5 rounded border border-slate-300 hover:bg-slate-200">
                        🔄 Refresh Logs
                    </button>
                </div>

                <!-- Stats summary -->
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                    <div class="bg-slate-50 p-3 rounded-lg border border-slate-200">
                        <p class="text-xs text-slate-500">Total Calls</p>
                        <p id="stat-total" class="text-lg font-bold text-slate-900">-</p>
                    </div>
                    <div class="bg-slate-50 p-3 rounded-lg border border-slate-200">
                        <p class="text-xs text-slate-500">Avg Latency</p>
                        <p id="stat-latency" class="text-lg font-bold text-blue-600">-</p>
                    </div>
                    <div class="bg-slate-50 p-3 rounded-lg border border-slate-200">
                        <p class="text-xs text-slate-500">Total Tokens</p>
                        <p id="stat-tokens" class="text-lg font-bold text-slate-900">-</p>
                    </div>
                    <div class="bg-slate-50 p-3 rounded-lg border border-slate-200">
                        <p class="text-xs text-slate-500">Errors / Blocks</p>
                        <p id="stat-errors" class="text-lg font-bold text-red-600">-</p>
                    </div>
                </div>

                <!-- Logs Table -->
                <div class="overflow-x-auto border border-slate-200 rounded-lg">
                    <table class="w-full text-left text-xs text-slate-700">
                        <thead class="bg-slate-100 text-slate-600 font-semibold border-b border-slate-200">
                            <tr>
                                <th class="p-2.5">ID</th>
                                <th class="p-2.5">Agent / Action</th>
                                <th class="p-2.5">Status</th>
                                <th class="p-2.5">Duration</th>
                                <th class="p-2.5">Tokens</th>
                                <th class="p-2.5">Prompt Preview</th>
                            </tr>
                        </thead>
                        <tbody id="logs-tbody" class="divide-y divide-slate-100">
                            <tr><td colspan="6" class="p-4 text-center text-slate-400">Loading tracking data...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
    </main>

    <!-- Client-Side JavaScript -->
    <script>
        let currentSessionId = 'sess_' + Math.random().toString(36).substring(2, 10);
        let activeToken = '';
        let activeHeader = 'x-api-key';

        function switchTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('nav button').forEach(el => {
                el.classList.remove('border-blue-600', 'text-blue-600', 'font-semibold');
                el.classList.add('border-transparent', 'text-slate-500');
            });
            document.getElementById('tab-' + tabId).classList.add('active');
            const btn = document.getElementById('tab-btn-' + tabId);
            btn.classList.add('border-blue-600', 'text-blue-600', 'font-semibold');
            btn.classList.remove('border-transparent', 'text-slate-500');

            if (tabId === 'logs') loadLogs();
            if (tabId === 'guardrail') loadGuardrails();
            if (tabId === 'config') loadActiveConfig();
        }

        async function loadActiveConfig() {
            try {
                const res = await fetch('/api/connections/active');
                if (res.ok) {
                    const data = await res.json();
                    document.getElementById('cfg-name').value = data.connection_name || '';
                    document.getElementById('cfg-url').value = data.base_url || window.location.origin;
                    document.getElementById('cfg-header').value = data.header_name || 'x-api-key';
                    document.getElementById('cfg-token').value = data.api_token || '';
                    document.getElementById('cfg-model').value = data.model_name || 'beam:cloud';
                    document.getElementById('cfg-ollama-url').value = data.ollama_base_url || 'https://ollama.com/api/chat';
                    activeToken = data.api_token;
                    activeHeader = data.header_name || 'x-api-key';
                    document.getElementById('active-model-tag').innerText = data.model_name || 'beam:cloud';
                }
            } catch (e) {
                console.error(e);
            }
        }

        function generateRandomToken() {
            const arr = new Uint8Array(16);
            window.crypto.getRandomValues(arr);
            const hex = Array.from(arr).map(b => b.toString(16).padStart(2, '0')).join('');
            document.getElementById('cfg-token').value = 'beam_sec_' + hex;
        }

        function autoGenerateConfig() {
            const rand = Math.random().toString(36).substring(2, 7).toUpperCase();
            document.getElementById('cfg-name').value = 'Beam-Vercel-Tracker-' + rand;
            document.getElementById('cfg-url').value = window.location.origin;
            generateRandomToken();
            document.getElementById('cfg-header').value = 'x-api-key';
            document.getElementById('cfg-model').value = 'beam:cloud';
            saveConfiguration();
        }

        async function saveConfiguration() {
            const alertBox = document.getElementById('cfg-alert');
            const payload = {
                connection_name: document.getElementById('cfg-name').value,
                base_url: document.getElementById('cfg-url').value,
                header_name: document.getElementById('cfg-header').value,
                api_token: document.getElementById('cfg-token').value,
                model_name: document.getElementById('cfg-model').value,
                ollama_base_url: document.getElementById('cfg-ollama-url').value,
                is_active: true
            };
            try {
                const res = await fetch('/api/connections/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    const d = await res.json();
                    activeToken = payload.api_token;
                    activeHeader = payload.header_name;
                    alertBox.className = 'text-xs p-3 rounded-lg font-medium bg-emerald-100 text-emerald-800 border border-emerald-200 block';
                    alertBox.innerText = '✅ Saved to Neon PostgreSQL & Activated! Connection: ' + payload.connection_name;
                } else {
                    throw new Error('Failed to save');
                }
            } catch (err) {
                alertBox.className = 'text-xs p-3 rounded-lg font-medium bg-red-100 text-red-800 border border-red-200 block';
                alertBox.innerText = '❌ Error saving: ' + err.message;
            }
        }

        async function pingHealth() {
            const alertBox = document.getElementById('cfg-alert');
            try {
                const res = await fetch('/api/health');
                const data = await res.json();
                alertBox.className = 'text-xs p-3 rounded-lg font-medium bg-blue-100 text-blue-800 border border-blue-200 block';
                alertBox.innerText = 'Health 200 OK: Status=' + data.status + ', DB=' + data.database + ', ActiveModel=' + data.active_model;
            } catch (e) {
                alertBox.className = 'text-xs p-3 rounded-lg font-medium bg-red-100 text-red-800 border border-red-200 block';
                alertBox.innerText = 'Ping failed: ' + e.message;
            }
        }

        async function sendMessage(e) {
            e.preventDefault();
            const input = document.getElementById('user-input');
            const prompt = input.value.trim();
            if (!prompt) return;

            input.value = '';
            document.getElementById('kill-session-id').value = currentSessionId;

            const chatBox = document.getElementById('chat-messages');
            
            // Append User message
            chatBox.innerHTML += `
                <div class="flex items-start space-x-3 justify-end">
                    <div class="bg-blue-600 text-white rounded-lg p-3 text-sm max-w-2xl">${escapeHtml(prompt)}</div>
                    <div class="w-8 h-8 rounded-full bg-slate-400 text-white flex items-center justify-center font-bold text-xs shrink-0">U</div>
                </div>
            `;
            chatBox.scrollTop = chatBox.scrollHeight;

            // Loading placeholder
            const msgId = 'resp_' + Date.now();
            chatBox.innerHTML += `
                <div id="${msgId}" class="flex items-start space-x-3">
                    <div class="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-xs shrink-0">AI</div>
                    <div class="bg-slate-100 rounded-lg p-3 text-sm max-w-2xl text-slate-800">
                        <span class="animate-pulse">Thinking with Ollama beam:cloud... ⏳</span>
                    </div>
                </div>
            `;
            chatBox.scrollTop = chatBox.scrollHeight;

            const headers = { 'Content-Type': 'application/json' };
            if (activeToken) headers[activeHeader] = activeToken;

            try {
                const res = await fetch('/api/agent/run', {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({
                        agent_name: document.getElementById('agent-name-input').value || 'Beam-Agent',
                        action: 'chat_execution',
                        step_number: 1,
                        messages: [{ role: 'user', content: prompt }],
                        session_id: currentSessionId
                    })
                });

                const data = await res.json();
                const respEl = document.getElementById(msgId);
                
                if (res.ok) {
                    let contentHtml = '';
                    if (data.thinking) {
                        contentHtml += `<details class="mb-2 text-xs text-slate-500 bg-slate-200/60 p-2 rounded cursor-pointer"><summary class="font-semibold">🧠 Beam Cloud Reasoning Trace</summary><pre class="mt-1 whitespace-pre-wrap font-mono">${escapeHtml(data.thinking)}</pre></details>`;
                    }
                    if (data.is_intercepted) {
                        contentHtml += `<div class="p-2.5 bg-amber-50 border border-amber-200 rounded text-amber-800 font-medium">⚠️ [INTERCEPTED] ${escapeHtml(data.content)}</div>`;
                    } else {
                        contentHtml += `<div>${escapeHtml(data.content)}</div>`;
                    }
                    contentHtml += `<div class="mt-1 text-[10px] text-slate-400">⚡ ${Math.round(data.total_duration_ms || 0)} ms | Prompt: ${data.prompt_tokens || 0} tok | Done: ${data.completion_tokens || 0} tok</div>`;
                    respEl.querySelector('div:last-child').innerHTML = contentHtml;
                } else {
                    respEl.querySelector('div:last-child').innerHTML = `<span class="text-red-600 font-semibold">Error (${res.status}): ${escapeHtml(data.detail || 'Request failed')}</span>`;
                }
            } catch (err) {
                document.getElementById(msgId).querySelector('div:last-child').innerHTML = `<span class="text-red-600 font-semibold">Failed to reach server: ${escapeHtml(err.message)}</span>`;
            }
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        async function triggerKillSwitch() {
            const sid = document.getElementById('kill-session-id').value.trim() || currentSessionId;
            const reason = document.getElementById('kill-reason').value.trim();
            const resBox = document.getElementById('kill-result');

            const headers = { 'Content-Type': 'application/json' };
            if (activeToken) headers[activeHeader] = activeToken;

            try {
                const res = await fetch('/api/agent/stop', {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({ session_id: sid, reason: reason })
                });
                const d = await res.json();
                resBox.className = 'text-xs p-2.5 rounded border bg-red-50 text-red-700 border-red-200 block';
                resBox.innerText = '🛑 Kill signal sent: ' + d.message;
            } catch (err) {
                resBox.className = 'text-xs p-2.5 rounded border bg-red-50 text-red-700 border-red-200 block';
                resBox.innerText = 'Error stopping: ' + err.message;
            }
        }

        async function loadGuardrails() {
            const container = document.getElementById('guardrails-list');
            const headers = {};
            if (activeToken) headers[activeHeader] = activeToken;

            try {
                const res = await fetch('/api/guardrails', { headers: headers });
                if (res.ok) {
                    const rules = await res.json();
                    if (!rules || rules.length === 0) {
                        container.innerHTML = '<p class="text-slate-400">No active rules.</p>';
                        return;
                    }
                    container.innerHTML = rules.map(r => `
                        <div class="p-2.5 border border-slate-200 rounded-lg flex items-center justify-between bg-slate-50">
                            <div>
                                <span class="font-bold text-slate-800">${escapeHtml(r.rule_name)}</span>
                                <span class="text-[10px] bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded ml-2">${r.action}</span>
                                <p class="text-[11px] text-slate-500 font-mono mt-0.5">${escapeHtml(r.pattern)}</p>
                            </div>
                            <span class="${r.is_active ? 'text-emerald-600 font-bold' : 'text-slate-400'}">${r.is_active ? 'Active' : 'Disabled'}</span>
                        </div>
                    `).join('');
                }
            } catch (e) {
                container.innerHTML = '<p class="text-red-500">Could not load rules: ' + e.message + '</p>';
            }
        }

        async function loadLogs() {
            const tbody = document.getElementById('logs-tbody');
            const headers = {};
            if (activeToken) headers[activeHeader] = activeToken;

            try {
                // Fetch stats
                fetch('/api/tracking/stats', { headers: headers }).then(r => r.json()).then(s => {
                    document.getElementById('stat-total').innerText = s.total_requests || 0;
                    document.getElementById('stat-latency').innerText = Math.round(s.avg_latency_ms || 0) + ' ms';
                    document.getElementById('stat-tokens').innerText = (s.total_prompt_tokens || 0) + (s.total_completion_tokens || 0);
                    document.getElementById('stat-errors').innerText = s.error_count || 0;
                }).catch(() => {});

                // Fetch logs
                const res = await fetch('/api/tracking/logs?limit=25', { headers: headers });
                if (res.ok) {
                    const data = await res.json();
                    const logs = data.logs || [];
                    if (logs.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="6" class="p-4 text-center text-slate-400">No tracking logs found.</td></tr>';
                        return;
                    }
                    tbody.innerHTML = logs.map(l => {
                        let statusBadge = '<span class="px-1.5 py-0.5 rounded text-[10px] bg-emerald-100 text-emerald-800 font-semibold">success</span>';
                        if (l.status === 'intercepted') statusBadge = '<span class="px-1.5 py-0.5 rounded text-[10px] bg-amber-100 text-amber-800 font-semibold">intercepted</span>';
                        if (l.status === 'aborted' || l.status === 'error') statusBadge = '<span class="px-1.5 py-0.5 rounded text-[10px] bg-red-100 text-red-800 font-semibold">' + l.status + '</span>';

                        return `
                            <tr class="hover:bg-slate-50 transition">
                                <td class="p-2.5 font-mono text-slate-500">#${l.id}</td>
                                <td class="p-2.5 font-medium text-slate-800">${escapeHtml(l.agent_name || 'Agent')} <span class="text-slate-400">(${escapeHtml(l.action || '-')})</span></td>
                                <td class="p-2.5">${statusBadge}</td>
                                <td class="p-2.5 font-mono text-slate-600">${Math.round(l.total_duration_ms || 0)} ms</td>
                                <td class="p-2.5 font-mono text-slate-600">${(l.prompt_eval_count || 0) + (l.eval_count || 0)}</td>
                                <td class="p-2.5 text-slate-500 truncate max-w-xs">${escapeHtml(l.prompt || '-')}</td>
                            </tr>
                        `;
                    }).join('');
                }
            } catch (e) {
                tbody.innerHTML = '<tr><td colspan="6" class="p-4 text-center text-red-500">Error loading logs: ' + e.message + '</td></tr>';
            }
        }

        function clearChat() {
            document.getElementById('chat-messages').innerHTML = `
                <div class="flex items-start space-x-3">
                    <div class="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-xs shrink-0">AI</div>
                    <div class="bg-slate-100 rounded-lg p-3 text-sm max-w-2xl text-slate-800">
                        Chat reset. You can start a fresh conversation!
                    </div>
                </div>
            `;
            currentSessionId = 'sess_' + Math.random().toString(36).substring(2, 10);
            document.getElementById('kill-session-id').value = currentSessionId;
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        // Initialize on page load
        window.onload = function() {
            loadActiveConfig();
        };
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def serve_home():
    """Serves the complete minimal web UI on Vercel at root '/'."""
    return HTML_UI

