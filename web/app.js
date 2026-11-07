/**
 * Subtitle Maker — Frontend Application Controller
 * Handles interactive file upload, live progress tracking,
 * HTML5 video player synchronization, live subtitle editing, and exports.
 */

(() => {
  'use strict';

  // State
  let currentFile = null;
  let currentJobId = null;
  let pollInterval = null;
  let currentCues = [];
  let detectedLanguage = 'id';

  // DOM Elements
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // Status & Navigation
  const statusText = $('#statusText');
  const navTabs = $$('.nav-tab');
  const tabContents = $$('.tab-content');

  // Tab 1: Generate
  const dropZone = $('#dropZone');
  const fileInput = $('#fileInput');
  const stagedFileCard = $('#stagedFileCard');
  const stagedFileName = $('#stagedFileName');
  const stagedFileSize = $('#stagedFileSize');
  const cancelStagedBtn = $('#cancelStagedBtn');
  const narrationToggle = $('#narrationToggle');
  const narrationBody = $('#narrationBody');
  const narrationArrow = $('#narrationArrow');
  const narrationText = $('#narrationText');
  const narrationCharCount = $('#narrationCharCount');
  const clearNarrationBtn = $('#clearNarrationBtn');
  const languageSelect = $('#languageSelect');
  const modelSelect = $('#modelSelect');
  const presetBtns = $$('.preset-btn');
  const customCharLimit = $('#customCharLimit');
  const generateBtn = $('#generateBtn');
  const progressCard = $('#progressCard');
  const progressStageText = $('#progressStageText');
  const progressPercent = $('#progressPercent');
  const progressBarFill = $('#progressBarFill');
  const progressDetail = $('#progressDetail');
  const recentBanner = $('#recentBanner');
  const recentBannerName = $('#recentBannerName');
  const recentBannerInfo = $('#recentBannerInfo');
  const recentOpenBtn = $('#recentOpenBtn');
  const recentProjectsContainer = $('#recentProjectsContainer');
  const recentProjectsList = $('#recentProjectsList');

  // Tab 2: Editor & Player
  const emptyEditorState = $('#emptyEditorState');
  const editorContainer = $('#editorContainer');
  const goToGenerateBtn = $('#goToGenerateBtn');
  const mediaPlayer = $('#mediaPlayer');
  const subtitleOverlay = $('#subtitleOverlay');
  const playerTime = $('#playerTime');
  const cuesCountBadge = $('#cuesCountBadge');
  const cuesList = $('#cuesList');
  const addNewCueBtn = $('#addNewCueBtn');
  const dlSrtBtn = $('#dlSrtBtn');
  const dlVttBtn = $('#dlVttBtn');
  const dlAssBtn = $('#dlAssBtn');
  const dlTxtBtn = $('#dlTxtBtn');
  const copySrtBtn = $('#copySrtBtn');

  // Tab 3: Vocabulary
  const vocabForm = $('#vocabForm');
  const rawInput = $('#rawInput');
  const correctedInput = $('#correctedInput');
  const domainInput = $('#domainInput');
  const vocabTableBody = $('#vocabTableBody');

  // Tab 4: Diagnostics
  const refreshDiagBtn = $('#refreshDiagBtn');
  const diagFFmpeg = $('#diagFFmpeg');
  const diagWhisper = $('#diagWhisper');
  const diagCachePath = $('#diagCachePath');
  const audioReportSection = $('#audioReportSection');
  const metricScore = $('#metricScore');
  const metricDuration = $('#metricDuration');
  const metricNoise = $('#metricNoise');
  const metricCoverage = $('#metricCoverage');

  // Toast Container
  const toastContainer = $('#toastContainer');

  // ── Toast Notification Helper ──
  function showToast(message, duration = 3000) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // ── Formatting Helpers ──
  function formatSeconds(sec) {
    if (isNaN(sec) || sec < 0) sec = 0;
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    const ms = Math.floor((sec % 1) * 10);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${ms}`;
  }

  function parseFormattedTime(str) {
    if (!str) return 0.0;
    // Format could be MM:SS.ms, HH:MM:SS,mmm or HH:MM:SS.mmm
    const parts = str.trim().replace(',', '.').split(':');
    if (parts.length === 3) {
      return parseFloat(parts[0]) * 3600 + parseFloat(parts[1]) * 60 + parseFloat(parts[2]);
    } else if (parts.length === 2) {
      return parseFloat(parts[0]) * 60 + parseFloat(parts[1]);
    }
    return parseFloat(str) || 0.0;
  }

  // ── Tab Navigation ──
  function switchTab(targetId) {
    navTabs.forEach((tab) => {
      tab.classList.toggle('active', tab.getAttribute('data-target') === targetId);
    });
    tabContents.forEach((tc) => {
      tc.classList.toggle('active', tc.id === targetId);
    });

    if (targetId === 'tab-vocab') {
      loadVocabulary();
    } else if (targetId === 'tab-diag') {
      loadDiagnostics();
    }
  }

  navTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      switchTab(tab.getAttribute('data-target'));
    });
  });

  if (goToGenerateBtn) {
    goToGenerateBtn.addEventListener('click', () => switchTab('tab-generate'));
  }

  // ── Narration Script Collapsible ──
  narrationToggle.addEventListener('click', () => {
    const isHidden = narrationBody.style.display === 'none';
    narrationBody.style.display = isHidden ? 'block' : 'none';
    narrationArrow.textContent = isHidden ? '▾' : '▸';
  });

  narrationText.addEventListener('input', () => {
    const len = narrationText.value.length;
    narrationCharCount.textContent = `${len.toLocaleString('id-ID')} karakter`;
  });

  clearNarrationBtn.addEventListener('click', () => {
    narrationText.value = '';
    narrationCharCount.textContent = '0 karakter';
  });

  // ── Segmentation Presets ──
  presetBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      presetBtns.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      const limit = btn.getAttribute('data-limit');
      customCharLimit.value = limit === '0' ? '' : limit;
    });
  });

  customCharLimit.addEventListener('input', () => {
    presetBtns.forEach((b) => b.classList.remove('active'));
  });

  // ── Drag & Drop File Upload ──
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach((eventName) => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
  });

  ['dragenter', 'dragover'].forEach((eventName) => {
    dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'));
  });

  ['dragleave', 'drop'].forEach((eventName) => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'));
  });

  dropZone.addEventListener('click', () => fileInput.click());

  dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      stageFile(files[0]);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      stageFile(fileInput.files[0]);
    }
  });

  function stageFile(file) {
    currentFile = file;
    stagedFileName.textContent = file.name;
    const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
    stagedFileSize.textContent = `${sizeMb} MB`;
    stagedFileCard.style.display = 'flex';
    dropZone.style.display = 'none';
    generateBtn.style.display = 'block';
  }

  cancelStagedBtn.addEventListener('click', () => {
    currentFile = null;
    fileInput.value = '';
    stagedFileCard.style.display = 'none';
    dropZone.style.display = 'block';
    generateBtn.style.display = 'none';
  });

  // ── Transcription Trigger ──
  generateBtn.addEventListener('click', () => {
    if (!currentFile) {
      showToast('⚠️ Silakan pilih file media terlebih dahulu.');
      return;
    }

    const formData = new FormData();
    formData.append('file', currentFile);
    formData.append('language', languageSelect.value);
    formData.append('model', modelSelect.value);
    formData.append('narration', narrationText.value.trim());
    formData.append('charLimit', customCharLimit.value.trim());

    generateBtn.style.display = 'none';
    progressCard.style.display = 'block';
    progressBarFill.style.width = '2%';
    progressPercent.textContent = '2%';
    progressStageText.textContent = 'Mengunggah file media...';
    progressDetail.textContent = 'Mempersiapkan pengiriman file ke engine...';

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/transcribe', true);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const uploadPct = Math.round((e.loaded / e.total) * 100);
        // Map upload to 0-15% of total task
        const mappedPct = Math.max(2, Math.round((uploadPct / 100) * 15));
        progressBarFill.style.width = `${mappedPct}%`;
        progressPercent.textContent = `${mappedPct}%`;
        const loadedMb = (e.loaded / (1024 * 1024)).toFixed(1);
        const totalMb = (e.total / (1024 * 1024)).toFixed(1);
        progressStageText.textContent = `Mengunggah file media (${uploadPct}%)...`;
        progressDetail.textContent = `Terkirim: ${loadedMb} MB dari ${totalMb} MB`;
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText);
          currentJobId = data.jobId;
          progressStageText.textContent = 'Memulai proses transkripsi...';
          startProgressPolling(currentJobId);
        } catch (e) {
          progressCard.style.display = 'none';
          generateBtn.style.display = 'block';
          showToast('❌ Respon server tidak valid');
        }
      } else {
        progressCard.style.display = 'none';
        generateBtn.style.display = 'block';
        showToast(`❌ Gagal: ${xhr.statusText}`);
      }
    };

    xhr.onerror = () => {
      progressCard.style.display = 'none';
      generateBtn.style.display = 'block';
      showToast('❌ Koneksi terputus ke server lokal.');
    };

    xhr.send(formData);
  });

  // ── Progress Polling ──
  function startProgressPolling(jobId) {
    if (pollInterval) clearInterval(pollInterval);
    let consecutiveErrors = 0;

    pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/progress/${jobId}`);
        if (!res.ok) {
          consecutiveErrors++;
          if (consecutiveErrors >= 8) {
            clearInterval(pollInterval);
            progressCard.style.display = 'none';
            generateBtn.style.display = 'block';
            showToast(`❌ Gagal mengambil status (HTTP ${res.status}). Silakan muat ulang halaman.`);
          }
          return;
        }
        consecutiveErrors = 0;

        const data = await res.json();
        const pct = data.progress || 0;
        progressBarFill.style.width = `${pct}%`;
        progressPercent.textContent = `${pct}%`;
        progressStageText.textContent = data.message || 'Memproses...';

        if (data.status === 'completed') {
          clearInterval(pollInterval);
          showToast('✅ Subtitle berhasil dibuat!');
          loadRecentProjects();
          setTimeout(() => {
            progressCard.style.display = 'none';
            generateBtn.style.display = 'block';
            loadCompletedJob(data);
          }, 800);
        } else if (data.status === 'failed') {
          clearInterval(pollInterval);
          progressCard.style.display = 'none';
          generateBtn.style.display = 'block';
          showToast(`❌ Transkripsi gagal: ${data.error || 'Unknown error'}`);
        }
      } catch (e) {
        console.error('Polling error:', e);
        consecutiveErrors++;
        if (consecutiveErrors >= 10) {
          clearInterval(pollInterval);
          progressCard.style.display = 'none';
          generateBtn.style.display = 'block';
          showToast('❌ Koneksi terputus saat memeriksa progres.');
        }
      }
    }, 500);
  }

  // ── Load Completed Job into Editor ──
  function loadCompletedJob(jobData) {
    const res = jobData.result || {};
    currentCues = res.cues || [];
    detectedLanguage = res.language || 'id';

    // Update Diagnostics Report
    if (res.diagnostics) {
      audioReportSection.style.display = 'block';
      metricScore.textContent = `${res.diagnostics.qualityScore || 100}%`;
      metricDuration.textContent = `${res.duration || 0}s`;
      metricNoise.textContent = res.diagnostics.noiseLevel || 0.0;
      metricCoverage.textContent = `${Math.round((res.diagnostics.speechCoverage || 0) * 100)}%`;
    }

    // Load media player
    mediaPlayer.src = `/api/media/${jobData.jobId}`;
    mediaPlayer.load();

    // Show editor UI
    emptyEditorState.style.display = 'none';
    editorContainer.style.display = 'grid';
    renderCuesList();

    // Switch to Editor Tab
    switchTab('tab-editor');
  }

  // ── Render Cues in Editor ──
  function renderCuesList() {
    cuesCountBadge.textContent = currentCues.length;
    cuesList.innerHTML = '';

    if (currentCues.length === 0) {
      cuesList.innerHTML = '<p class="empty-state">Tidak ada baris subtitle.</p>';
      return;
    }

    currentCues.forEach((cue, index) => {
      const card = document.createElement('div');
      card.className = 'cue-card';
      card.id = `cue-${index}`;

      const cpsClass = cue.cps > 25 ? 'cue-cps-fast' : 'cue-cps-good';

      card.innerHTML = `
        <div class="cue-top">
          <span class="cue-index">#${index + 1}</span>
          <div class="cue-timing">
            <input type="text" class="cue-time-input cue-start" value="${formatSeconds(cue.start)}" title="Waktu Mulai">
            <span style="color: var(--text-muted);">➔</span>
            <input type="text" class="cue-time-input cue-end" value="${formatSeconds(cue.end)}" title="Waktu Selesai">
            <span class="cue-cps-badge ${cpsClass}" title="Karakter per Detik">${cue.cps || 0} cps</span>
          </div>
          <div class="cue-actions">
            <button class="btn-icon-sm play-cue-btn" title="Putar pada baris ini">▶️</button>
            <button class="btn-icon-sm del-cue-btn" title="Hapus baris ini">🗑️</button>
          </div>
        </div>
        <textarea class="cue-text-input" rows="${(cue.lines && cue.lines.length > 1) ? 2 : 1}">${cue.text}</textarea>
      `;

      // Event: Play at cue
      card.querySelector('.play-cue-btn').addEventListener('click', () => {
        mediaPlayer.currentTime = cue.start;
        mediaPlayer.play();
      });

      // Event: Delete cue
      card.querySelector('.del-cue-btn').addEventListener('click', () => {
        currentCues.splice(index, 1);
        renderCuesList();
        showToast(`Baris #${index + 1} dihapus.`);
      });

      // Event: Change text
      const textInput = card.querySelector('.cue-text-input');
      textInput.addEventListener('input', () => {
        cue.text = textInput.value;
        cue.lines = textInput.value.split('\n');
        cue.cps = Math.round((cue.text.length / Math.max(0.1, cue.end - cue.start)) * 10) / 10;
        const badge = card.querySelector('.cue-cps-badge');
        badge.textContent = `${cue.cps} cps`;
        badge.className = `cue-cps-badge ${cue.cps > 25 ? 'cue-cps-fast' : 'cue-cps-good'}`;
      });

      // Event: Change timing
      const startInput = card.querySelector('.cue-start');
      const endInput = card.querySelector('.cue-end');

      startInput.addEventListener('change', () => {
        cue.start = parseFormattedTime(startInput.value);
        cue.duration = Math.max(0.1, cue.end - cue.start);
      });

      endInput.addEventListener('change', () => {
        cue.end = parseFormattedTime(endInput.value);
        cue.duration = Math.max(0.1, cue.end - cue.start);
      });

      cuesList.appendChild(card);
    });
  }

  // ── Synchronize Media Player with Subtitle Overlay ──
  mediaPlayer.addEventListener('timeupdate', () => {
    const curTime = mediaPlayer.currentTime;
    playerTime.textContent = `⏱️ ${formatSeconds(curTime)} / ${formatSeconds(mediaPlayer.duration || 0)}`;

    let activeCue = null;
    let activeIdx = -1;

    for (let i = 0; i < currentCues.length; i++) {
      if (curTime >= currentCues[i].start && curTime <= currentCues[i].end) {
        activeCue = currentCues[i];
        activeIdx = i;
        break;
      }
    }

    // Update overlay text
    if (activeCue) {
      subtitleOverlay.textContent = activeCue.text;
    } else {
      subtitleOverlay.textContent = '';
    }

    // Highlight cue in list
    $$('.cue-card').forEach((c) => c.classList.remove('active-playing'));
    if (activeIdx !== -1) {
      const activeEl = document.getElementById(`cue-${activeIdx}`);
      if (activeEl) {
        activeEl.classList.add('active-playing');
      }
    }
  });

  // ── Add New Cue ──
  addNewCueBtn.addEventListener('click', () => {
    const curTime = mediaPlayer.currentTime || 0.0;
    const newCue = {
      index: currentCues.length,
      start: roundTo3(curTime),
      end: roundTo3(curTime + 2.0),
      duration: 2.0,
      text: 'Teks subtitle baru...',
      lines: ['Teks subtitle baru...'],
      cps: 10,
      confidence: 100,
      speaker: 'Speaker 1',
    };
    currentCues.push(newCue);
    currentCues.sort((a, b) => a.start - b.start);
    renderCuesList();
    showToast('Baris subtitle baru ditambahkan.');
  });

  function roundTo3(num) {
    return Math.round(num * 1000) / 1000;
  }

  // ── Shift Timestamps Offset ──
  function shiftAllTimestamps(deltaSeconds) {
    if (currentCues.length === 0) return;
    currentCues.forEach((c) => {
      c.start = Math.max(0, roundTo3(c.start + deltaSeconds));
      c.end = Math.max(0.1, roundTo3(c.end + deltaSeconds));
    });
    renderCuesList();
    showToast(`Semua timestamp digeser ${deltaSeconds > 0 ? '+' : ''}${Math.round(deltaSeconds * 1000)}ms`);
  }

  $('#shiftMinus500').addEventListener('click', () => shiftAllTimestamps(-0.5));
  $('#shiftMinus100').addEventListener('click', () => shiftAllTimestamps(-0.1));
  $('#shiftPlus100').addEventListener('click', () => shiftAllTimestamps(0.1));
  $('#shiftPlus500').addEventListener('click', () => shiftAllTimestamps(0.5));

  // ── Export / Download Handlers ──
  async function downloadFormat(fmt) {
    if (!currentJobId && currentCues.length === 0) {
      showToast('⚠️ Belum ada subtitle yang dimuat.');
      return;
    }

    // Export with latest edited cues
    try {
      const res = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cues: currentCues,
          format: fmt,
          language: detectedLanguage,
        }),
      });

      if (!res.ok) throw new Error('Gagal export subtitle');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const baseName = currentFile ? currentFile.name.replace(/\.[^/.]+$/, '') : 'subtitle';
      a.download = `${baseName}.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      showToast(`📥 File ${fmt.toUpperCase()} berhasil diunduh!`);
    } catch (e) {
      showToast(`❌ Error: ${e.message}`);
    }
  }

  dlSrtBtn.addEventListener('click', () => downloadFormat('srt'));
  dlVttBtn.addEventListener('click', () => downloadFormat('vtt'));
  dlAssBtn.addEventListener('click', () => downloadFormat('ass'));
  dlTxtBtn.addEventListener('click', () => downloadFormat('txt'));

  copySrtBtn.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cues: currentCues,
          format: 'srt',
          language: detectedLanguage,
        }),
      });
      const text = await res.text();
      await navigator.clipboard.writeText(text);
      showToast('📋 Format SRT berhasil disalin ke clipboard!');
    } catch (e) {
      showToast('Gagal menyalin ke clipboard.');
    }
  });

  // ── Tab 3: Vocabulary Management ──
  async function loadVocabulary() {
    try {
      const res = await fetch('/api/vocabulary');
      if (!res.ok) return;
      const data = await res.json();
      renderVocabTable(data.rules || []);
    } catch (e) {
      console.error(e);
    }
  }

  function renderVocabTable(rules) {
    vocabTableBody.innerHTML = '';
    if (rules.length === 0) {
      vocabTableBody.innerHTML = '<tr><td colspan="4" class="empty-state-cell">Belum ada aturan terdaftar.</td></tr>';
      return;
    }

    rules.forEach((r, idx) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><code>${r.raw}</code></td>
        <td><strong style="color: #60a5fa;">${r.corrected}</strong></td>
        <td><span style="font-size: 0.8rem; color: var(--text-muted);">${r.domain || 'general'}</span></td>
        <td><button class="btn-cancel" style="padding: 2px 6px; font-size: 0.75rem;" data-idx="${idx}">Hapus</button></td>
      `;
      tr.querySelector('button').addEventListener('click', async () => {
        await deleteVocabulary(idx);
      });
      vocabTableBody.appendChild(tr);
    });
  }

  vocabForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const raw = rawInput.value.trim();
    const corrected = correctedInput.value.trim();
    const domain = domainInput.value;

    if (!raw || !corrected) return;

    try {
      const res = await fetch('/api/vocabulary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw, corrected, domain }),
      });
      if (res.ok) {
        rawInput.value = '';
        correctedInput.value = '';
        showToast('✅ Aturan koreksi berhasil disimpan.');
        loadVocabulary();
      }
    } catch (err) {
      showToast('Gagal menyimpan aturan.');
    }
  });

  async function deleteVocabulary(index) {
    try {
      const res = await fetch(`/api/vocabulary/${index}`, { method: 'DELETE' });
      if (res.ok) {
        showToast('Aturan dihapus.');
        loadVocabulary();
      }
    } catch (e) {
      showToast('Gagal menghapus aturan.');
    }
  }

  // ── Tab 4: Diagnostics & Health ──
  async function loadDiagnostics() {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) return;
      const data = await res.json();

      // Top Status Bar
      if (data.status === 'ready') {
        statusText.textContent = 'Engine Siap (FFmpeg + faster-whisper)';
      }

      // FFmpeg
      const ff = data.ffmpeg || {};
      diagFFmpeg.querySelector('.diag-desc').textContent = ff.ffmpeg
        ? `Tersedia (${ff.version || 'OK'}) • RNNoise Filter: ${ff.arnndn ? 'Aktif' : 'Standar'}`
        : 'Tidak ditemukan di PATH sistem';

      // Whisper
      diagWhisper.querySelector('.diag-desc').textContent = 'faster-whisper (CTranslate2 Int8 CPU) Siap Digunakan';

      // Cache Dir
      diagCachePath.textContent = data.model_cache || 'Default';
    } catch (e) {
      statusText.textContent = 'Engine Offline';
    }
  }

  if (refreshDiagBtn) {
    refreshDiagBtn.addEventListener('click', () => {
      loadDiagnostics();
      showToast('Status diagnostik diperbarui.');
    });
  }

  // ── Recent Projects Loader ──
  async function loadRecentProjects() {
    try {
      const res = await fetch('/api/recent');
      if (!res.ok) return;
      const data = await res.json();
      const items = data.items || [];
      if (items.length > 0) {
        const top = items[0];
        if (recentBanner && recentBannerName && recentBannerInfo && recentOpenBtn) {
          recentBannerName.textContent = top.filename || 'Subtitle Terakhir';
          recentBannerInfo.textContent = `${top.cues_count || 0} baris subtitle • Durasi ${top.duration ? Math.round(top.duration) + 's' : 'selesai'}`;
          recentBanner.style.display = 'flex';
          recentOpenBtn.onclick = () => loadJobById(top.id);
        }

        if (recentProjectsContainer && recentProjectsList) {
          recentProjectsContainer.style.display = 'block';
          recentProjectsList.innerHTML = '';
          items.forEach((item) => {
            const div = document.createElement('div');
            div.style.cssText = 'background: rgba(255,255,255,0.04); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.6rem 0.85rem; margin-bottom: 0.5rem; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: all 0.2s ease;';
            div.innerHTML = `
              <div>
                <strong style="color: #60a5fa; font-size: 0.9rem;">${item.filename}</strong>
                <div style="font-size: 0.75rem; color: var(--text-muted);">${item.cues_count} baris • ${Math.round(item.duration || 0)}s</div>
              </div>
              <button class="btn-primary" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;">Buka ➔</button>
            `;
            div.addEventListener('click', () => loadJobById(item.id));
            recentProjectsList.appendChild(div);
          });
        }
      } else {
        if (recentBanner) recentBanner.style.display = 'none';
        if (recentProjectsContainer) recentProjectsContainer.style.display = 'none';
      }
    } catch (e) {
      console.error('Failed to load recent projects', e);
    }
  }

  async function loadJobById(jobId) {
    showToast('⏳ Memuat proyek subtitle...');
    try {
      const res = await fetch(`/api/progress/${jobId}`);
      if (!res.ok) {
        showToast('❌ Proyek tidak ditemukan.');
        return;
      }
      const data = await res.json();
      currentJobId = jobId;
      loadCompletedJob(data);
    } catch (e) {
      showToast('❌ Gagal memuat proyek.');
    }
  }

  // ── Initial Start ──
  loadDiagnostics();
  loadRecentProjects();
})();
