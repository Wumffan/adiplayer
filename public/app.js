/**
 * AdiPlayer v5
 * 網易雲音樂播放器 - 大封面 + 純SVG控制 + 漸層自訂 + 循環模式
 */

const state = {
  wallOffset: 0, wallLimit: 20, wallEnd: false, wallLoading: false,
  searchKeyword: '', searchOffset: 0, searchLimit: 30, searchEnd: false,
  playlist: [], currentIndex: -1, isPlaying: false, progressTimer: null,
  loopMode: 'all', // 'all' | 'one' | 'shuffle'
  playFrom: '',   // 'wall' | 'search' | 'likes' 標識來源
  user: null,
  bgSettings: null,
  playerGradient: { color1: '#0f0f14', color2: '#1a0a1a', angle: 180 },
  likedIds: [],
  lastPlaylist: null, lastIndex: -1,
  sidebarOpen: false,
};

const $ = (id) => document.getElementById(id);
const $$ = (sel, root = document) => root.querySelectorAll(sel);

// ========= 基礎工具 =========
async function api(path, params = {}) {
  const qs = new URLSearchParams(params).toString();
  const url = qs ? `${path}?${qs}` : path;
  const res = await fetch(url, { credentials: 'include' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
function toast(msg, duration = 1800) {
  const el = $('toast');
  el.textContent = msg; el.classList.add('show');
  clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove('show'), duration);
}
function escapeHtml(s) {
  return String(s || '').replace(/[<>"]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
function formatTime(sec) {
  if (!sec || sec < 0) return '0:00';
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}
function updateClock() {
  const d = new Date();
  $('clock').textContent = `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
}

// ========= 側邊欄 =========
function openSidebar() {
  state.sidebarOpen = true;
  $('sidebar').classList.add('open');
  $('sidebarMask').classList.add('show');
  $('deviceFrame').classList.add('shifted');
}
function closeSidebar() {
  state.sidebarOpen = false;
  $('sidebar').classList.remove('open');
  $('sidebarMask').classList.remove('show');
  $('deviceFrame').classList.remove('shifted');
}

// ========= 專輯牆 =========
async function loadWall(reset = true) {
  if (state.wallLoading) return;
  if (reset) {
    state.wallOffset = 0; state.wallEnd = false;
    $('albumWall').innerHTML = ''; $('wallEnd').style.display = 'none';
  }
  if (state.wallEnd) return;
  state.wallLoading = true;
  try {
    const d = await api('/api/top/playlist', { order: 'all', limit: state.wallLimit, offset: state.wallOffset });
    const list = d.playlists || [];
    state.wallOffset += list.length;
    if (list.length < state.wallLimit) { state.wallEnd = true; $('wallEnd').style.display = 'block'; }
    renderWall(list);
  } catch (e) { toast('載入失敗: ' + e.message); }
  finally {
    state.wallLoading = false;
    $('wallLoading').style.display = state.wallEnd ? 'none' : 'block';
  }
}
function renderWall(items) {
  const wall = $('albumWall');
  const html = items.map((p) => `
    <div class="album-card" data-id="${p.id}">
      <img class="ac-cover" src="${p.coverImgUrl}" alt="" loading="lazy" />
      <div class="ac-info">
        <div class="ac-title">${escapeHtml(p.name)}</div>
        <div class="ac-sub">${escapeHtml(`by ${p.creator?.nickname || '官方'}`)}</div>
      </div>
      <div class="ac-play">▶</div>
    </div>`).join('');
  wall.insertAdjacentHTML('beforeend', html);
  wall.querySelectorAll('.album-card:not([data-bound])').forEach(card => {
    card.dataset.bound = '1';
    card.addEventListener('click', () => openPlaylist(card.dataset.id));
  });
}

// ========= Tab 切換 =========
function switchPage(page) {
  const currentEl = document.querySelector('.page.active');
  const nextEl = document.querySelector(`.page[data-page="${page}"]`);
  if (!nextEl || currentEl === nextEl) return;
  currentEl.classList.remove('active');
  setTimeout(() => {
    nextEl.classList.add('active', 'fresh');
    $$('.tab-item').forEach(t => t.classList.toggle('active', t.dataset.page === page));
    if (page === 'discover') loadWall(true);
    else if (page === 'search') initSearchFresh();
    setTimeout(() => nextEl.classList.remove('fresh'), 500);
  }, 350);
}

// ========= 歌曲字段正規化 (網易雲 API: al→album, ar→artists) =========
function normalizeSong(raw) {
  if (!raw) return null;
  const s = { ...raw };
  // album 圖片：優先 al.picUrl，否則用 album.picUrl
  if (!s.album || !s.album.picUrl) {
    s.album = {
      name: s.al?.name || s.album?.name || '',
      picUrl: s.al?.picUrl || s.album?.picUrl || '',
      picId: s.al?.pic || s.al?.pic_str || ''
    };
  }
  // artists：優先 ar 數組
  if (!s.artists || !s.artists.length) {
    s.artists = (s.ar || s.artists || []).map(a => ({ name: a.name || a }));
  }
  return s;
}

// ========= 歌單詳情 =========
async function openPlaylist(id) {
  const page = $('playlistPage');
  page.classList.add('show'); $('playerPage').classList.remove('show');
  $('plSongs').innerHTML = '<div style="text-align:center;padding:40px;color:#888">載入中...</div>';
  try {
    const d = await api('/api/playlist/detail', { id });
    const pl = d.playlist || {};
    const trackIds = (pl.trackIds || []).slice(0, 50);
    const details = await Promise.all(trackIds.map(t => api('/api/song/detail', { ids: t.id }).catch(() => null)));
    const songs = details.filter(Boolean).map(x => normalizeSong((x.songs || [])[0])).filter(Boolean);
    $('plBg').style.backgroundImage = `url(${pl.coverImgUrl})`;
    $('plBg').style.backgroundSize = 'cover';
    $('plCover').src = pl.coverImgUrl || '';
    $('plTitle').textContent = pl.name || '';
    $('plCreator').textContent = pl.creator?.nickname || '';
    $('plCount').textContent = `${songs.length} 首歌曲`;
    $('plSongs').innerHTML = songs.map((s, i) => `
      <li class="song-item" data-idx="${i}">
        <div class="song-num">${i + 1}</div>
        <div class="s-info">
          <div class="s-name">${escapeHtml(s.name)}</div>
          <div class="s-artist">${escapeHtml((s.artists || []).map(a => a.name).join(' / '))}</div>
        </div>
        <button class="s-play">▶</button>
      </li>`).join('');
    state.playlist = songs; state.currentIndex = -1; state.playFrom = 'wall';
    $('plSongs').querySelectorAll('.song-item').forEach(el => {
      el.addEventListener('click', () => playSong(parseInt(el.dataset.idx)));
    });
    $('plPlayBtn').onclick = () => songs.length && playSong(0);
  } catch (e) { toast('載入失敗: ' + e.message); page.classList.remove('show'); }
}

// ========= 播放器 =========
const audio = $('audioPlayer');

function loadDefaultCover() {
  const disc = $('coverDisc'); if (!disc) return;
  const gradientSvg = `<svg width="100%" height="100%" viewBox="0 0 260 260" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="defaultGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#1a1a1a"/><stop offset="50%" stop-color="#333"/><stop offset="100%" stop-color="#111"/></linearGradient><pattern id="noise" x="0" y="0" width="4" height="4" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="0.5" fill="rgba(255,255,255,0.04)"/><circle cx="3" cy="3" r="0.5" fill="rgba(255,255,255,0.06)"/></pattern></defs><rect width="260" height="260" fill="url(#defaultGrad)"/><rect width="260" height="260" fill="url(#noise)"/><circle cx="130" cy="130" r="60" fill="rgba(255,255,255,0.03)"/><circle cx="130" cy="130" r="18" fill="rgba(255,255,255,0.06)"/><circle cx="130" cy="130" r="4" fill="#000"/></svg>`;
  disc.innerHTML = `<div class="cover-img-fallback">${gradientSvg}</div><div class="cover-disc-center"></div>`;
  const pb = $('playerBg'); if (pb) pb.style.backgroundImage = 'linear-gradient(135deg,#1a1a1a,#0a0a0a)';
}

async function playSong(index) {
  if (!state.playlist[index]) return;
  state.currentIndex = index;
  const song = state.playlist[index];
  updatePlayerUI(song);
  $('plBg') && ($('plBg').style.backgroundImage = '');
  $('miniPlayer').classList.add('show');
  saveLastState();
  try {
    const urlData = await api('/api/song/url', { id: song.id, level: 'standard' });
    const url = urlData.data?.[0]?.url;
    if (!url) { toast('抱歉，這首歌暫時無法播放'); return; }
    audio.src = url; await audio.play();
    state.isPlaying = true;
  } catch (e) { toast('播放失敗: ' + e.message); }
}

function updatePlayerUI(song) {
  if (!song) {
    // 未播放狀態
    $('playerTitle').textContent = '未播放音樂';
    $('playerArtist').textContent = '—';
    $('mpTitle').textContent = '未播放'; $('mpArtist').textContent = '—';
    loadDefaultCover(); updateFavoriteUI(null); updatePlayPauseIcon(false);
    return;
  }
  const artists = (song.artists || []).map(a => a.name).join(' / ');
  const cover = song.album?.picUrl || '';
  $('mpTitle').textContent = song.name; $('mpArtist').textContent = artists;
  $('playerTitle').textContent = song.name; $('playerArtist').textContent = artists;
  const mpCover = $('mpCover'); mpCover.innerHTML = '';
  if (cover) { const img = document.createElement('img'); img.src = cover; mpCover.appendChild(img); }
  if (cover) {
    $('coverDisc').innerHTML = `<img class="cover-img" id="coverImg" src="${cover}" alt="" /><div class="cover-disc-center"></div>`;
    $('playerBg').style.backgroundImage = `url(${cover})`;
    $('playerBg').style.backgroundSize = 'cover';
  } else {
    loadDefaultCover();
  }
  $('coverImg') && ($('coverImg').style.display = '');
  updateFavoriteUI(song);
  renderQueue();
}

function updateFavoriteUI(song) {
  const icon = $('favHeart');
  if (song && state.likedIds.includes(song.id)) {
    icon.setAttribute('fill', 'currentColor');
    icon.style.color = '#ff6b6b';
  } else {
    icon.setAttribute('fill', 'none');
    icon.style.color = '';
  }
}

function toggleFavorite() {
  const song = state.playlist[state.currentIndex];
  if (!song) return toast('先播放一首歌曲吧');
  const idx = state.likedIds.indexOf(song.id);
  if (idx >= 0) { state.likedIds.splice(idx, 1); toast('已從喜愛移除'); }
  else { state.likedIds.push(song.id); toast('已加入喜愛'); }
  localStorage.setItem('folia_liked', JSON.stringify(state.likedIds));
  updateFavoriteUI(song);
}

function saveLastState() {
  if (state.playlist[state.currentIndex]) {
    const data = {
      playlist: state.playlist.map(s => ({ id: s.id, name: s.name, artists: s.artists, album: s.album })),
      currentIndex: state.currentIndex,
    };
    localStorage.setItem('folia_last', JSON.stringify(data));
  }
}
function restoreLastState() {
  try {
    const raw = localStorage.getItem('folia_last');
    if (!raw) return false;
    const d = JSON.parse(raw);
    if (d.playlist && d.playlist.length && d.currentIndex >= 0 && d.currentIndex < d.playlist.length) {
      state.playlist = d.playlist;
      state.currentIndex = d.currentIndex;
      const song = state.playlist[state.currentIndex];
      updatePlayerUI(song);
      $('miniPlayer').classList.add('show');
      return true;
    }
  } catch {}
  return false;
}

function setLoopMode(mode) {
  state.loopMode = mode;
  const loopAll = $('iconLoopAll'), loopOne = $('iconLoopOne'), shuffle = $('iconShuffle');
  loopAll.style.display = mode === 'all' ? '' : 'none';
  loopOne.style.display = mode === 'one' ? '' : 'none';
  shuffle.style.display = mode === 'shuffle' ? '' : 'none';
  const colors = { all: '#ffffff', one: '#ff6b6b', shuffle: '#66d9ef' };
  $('modeBtn').style.color = colors[mode] || '#fff';
  localStorage.setItem('folia_loop', mode);
}

function nextTrack() {
  if (!state.playlist.length) return;
  if (state.loopMode === 'shuffle') {
    let i;
    do { i = Math.floor(Math.random() * state.playlist.length); } while (state.playlist.length > 1 && i === state.currentIndex);
    playSong(i);
  } else if (state.loopMode === 'all') {
    playSong((state.currentIndex + 1) % state.playlist.length);
  } else {
    playSong((state.currentIndex + 1) % state.playlist.length);
  }
}
function prevTrack() {
  if (!state.playlist.length) return;
  if (state.loopMode === 'shuffle') {
    let i;
    do { i = Math.floor(Math.random() * state.playlist.length); } while (state.playlist.length > 1 && i === state.currentIndex);
    playSong(i);
  } else {
    playSong((state.currentIndex - 1 + state.playlist.length) % state.playlist.length);
  }
}

// 進度條拖动
let progressDragging = false;
function setupProgressBar() {
  const bar = $('progressBar');
  const fill = $('progressFill');
  const thumb = $('progressThumb');

  function setFromEvent(e) {
    const rect = bar.getBoundingClientRect();
    const clientX = (e.touches ? e.touches[0].clientX : e.clientX);
    let pct = (clientX - rect.left) / rect.width;
    pct = Math.max(0, Math.min(1, pct));
    fill.style.width = (pct * 100) + '%';
    thumb.style.left = (pct * 100) + '%';
    if (!progressDragging) {
      const dur = audio.duration || 1;
      audio.currentTime = pct * dur;
    }
  }
  bar.addEventListener('mousedown', (e) => { progressDragging = true; setFromEvent(e); });
  bar.addEventListener('touchstart', (e) => { progressDragging = true; setFromEvent(e); }, { passive: true });
  document.addEventListener('mousemove', (e) => { if (progressDragging) setFromEvent(e); });
  document.addEventListener('touchmove', (e) => { if (progressDragging) setFromEvent(e); }, { passive: true });
  document.addEventListener('mouseup', () => {
    if (progressDragging) { progressDragging = false; }
  });
  document.addEventListener('touchend', () => { progressDragging = false; });
}

function startProgressTimer() {
  stopProgressTimer();
  state.progressTimer = setInterval(() => {
    if (progressDragging) return;
    const cur = audio.currentTime || 0, dur = audio.duration || 0;
    $('progressFill').style.width = (dur ? (cur / dur * 100) : 0) + '%';
    $('progressThumb').style.left = (dur ? (cur / dur * 100) : 0) + '%';
    $('curTime').textContent = formatTime(cur); $('totTime').textContent = formatTime(dur);
  }, 300);
}
function stopProgressTimer() { if (state.progressTimer) { clearInterval(state.progressTimer); state.progressTimer = null; } }

function updatePlayPauseIcon(playing) {
  $('iconPlay').style.display = playing ? 'none' : '';
  $('iconPause').style.display = playing ? '' : 'none';
  $('playBtn').classList.toggle('playing', playing);
  $('mpPlayIcon').innerHTML = playing
    ? '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>'
    : '<path d="M8 5v14l11-7z"/>';
}

function togglePlay() {
  if (audio.paused) {
    if (state.currentIndex < 0) {
      if (state.playlist.length) playSong(0);
      else return toast('先選一首歌');
      return;
    }
    audio.play();
  } else {
    audio.pause();
  }
}

function renderQueue() {
  const listEl = $('queueList'); const empty = $('queueEmpty');
  if (!state.playlist.length) { empty.style.display = 'block'; listEl.innerHTML = ''; return; }
  empty.style.display = 'none';
  listEl.innerHTML = state.playlist.map((s, i) => `
    <li class="song-item ${i === state.currentIndex ? 'active-here' : ''}" data-idx="${i}">
      <div class="song-num">${i + 1}</div>
      <div class="s-info">
        <div class="s-name">${escapeHtml(s.name)}</div>
        <div class="s-artist">${escapeHtml((s.artists || []).map(a => a.name).join(' / '))}</div>
      </div>
      <button class="s-play">▶</button>
    </li>`).join('');
  listEl.querySelectorAll('.song-item').forEach(el => {
    el.addEventListener('click', () => playSong(parseInt(el.dataset.idx)));
  });
}

// ========= 搜尋 =========
async function initSearchFresh() {
  try {
    const d = await api('/api/search/hot');
    const hots = d.result?.hots || [];
    $('hotTags').innerHTML = hots.slice(0, 25).map(h =>
      `<span class="hot-tag" data-kw="${escapeHtml(h.first)}">${escapeHtml(h.first)}</span>`).join('');
    $('hotTags').querySelectorAll('.hot-tag').forEach(tag => {
      tag.addEventListener('click', () => {
        $('searchInput').value = tag.dataset.kw; $('searchClear').style.display = 'block';
        doSearch(tag.dataset.kw, true);
      });
    });
  } catch {}
  $('searchInput').value = ''; $('searchClear').style.display = 'none';
  $('searchResult').style.display = 'none'; $('searchSuggest').innerHTML = '';
}
let suggestTimer = null;
async function showSuggestions(keyword) {
  clearTimeout(suggestTimer); if (!keyword.trim()) { $('searchSuggest').innerHTML = ''; return; }
  suggestTimer = setTimeout(async () => {
    try {
      const d = await api('/api/search/suggest', { keywords: keyword });
      const r = d.result || {};
      const items = [
        ...(r.allMatch || []),
        ...(r.songs || []).slice(0, 3).map(s => ({ keyword: `${s.name} - ${(s.artists || []).map(a => a.name).join('/')}` }))
      ].slice(0, 6);
      if (!items.length) { $('searchSuggest').innerHTML = ''; return; }
      $('searchSuggest').innerHTML = items.map(s =>
        `<div class="suggest-item" data-kw="${escapeHtml(s.keyword)}">${escapeHtml(s.keyword)}</div>`).join('');
      $('searchSuggest').querySelectorAll('.suggest-item').forEach(el => {
        el.addEventListener('click', () => {
          const kw = el.dataset.kw.split(' - ')[0];
          $('searchInput').value = kw; $('searchSuggest').innerHTML = ''; doSearch(kw, true);
        });
      });
    } catch {}
  }, 350);
}
async function doSearch(keyword, reset = true) {
  if (!keyword.trim()) return;
  state.searchKeyword = keyword.trim();
  $('searchSuggest').innerHTML = ''; $('searchResult').style.display = 'block';
  if (reset) {
    state.searchOffset = 0; state.searchEnd = false;
    $('songList').innerHTML = ''; $('resultTitle').textContent = `"${keyword}" 的搜尋結果`;
  }
  if (state.searchEnd) return;
  try {
    const d = await api('/api/search', { keywords: state.searchKeyword, limit: state.searchLimit, offset: state.searchOffset, type: 1 });
    const songs = d.result?.songs || [];
    if (!songs.length) {
      if (reset) $('songList').innerHTML = '<div style="text-align:center;padding:40px;color:#888">沒有找到相關歌曲</div>';
      state.searchEnd = true; $('searchMore').style.display = 'none'; return;
    }
    state.playlist = songs.map(s => normalizeSong({
      id: s.id, name: s.name, ar: s.artists, al: s.album
    }));
    state.currentIndex = -1; state.playFrom = 'search';
    const html = songs.map((s, i) => {
      const globalIdx = state.searchOffset + i;
      return `<li class="song-item" data-idx="${globalIdx}">
        <div class="song-num">${globalIdx + 1}</div>
        <div class="s-info">
          <div class="s-name">${escapeHtml(s.name)}</div>
          <div class="s-artist">${escapeHtml((s.artists || []).map(a => a.name).join(' / '))}</div>
        </div>
        <button class="s-play">▶</button>
      </li>`;
    }).join('');
    $('songList').insertAdjacentHTML('beforeend', html);
    state.searchOffset += songs.length;
    if (songs.length < state.searchLimit) state.searchEnd = true;
    $('searchMore').style.display = state.searchEnd ? 'none' : 'block';
  } catch {
    if (reset) $('songList').innerHTML = '<div style="text-align:center;padding:40px;color:#888">搜尋失敗</div>';
  }
}

// ========= 登入 =========
// ========= 錯誤碼友好提示 =========
function friendlyLoginError(d) {
  if (!d) return '網絡錯誤';
  const code = d.code;
  if (code === -462) return '需要滑塊驗證，請嘗試二維碼登錄';
  if (code === 503) return '驗證碼錯誤，請重新發送';
  if (code === 509) return '密碼錯誤超過限制，請稍後再試或用二維碼登錄';
  if (code === 400) return '請求無效: ' + (d.message || '');
  return d.message || `登入失敗 (錯誤碼 ${code})`;
}

let qrTimer = null;
let qrKey = null;

async function refreshQR() {
  $('qrImg').style.display = 'none';
  $('qrLoading').style.display = '';
  $('qrLoading').textContent = '獲取中...';
  $('qrRefresh').style.display = 'none';
  stopQRPolling();
  try {
    const kd = await api('/api/login/qr/key');
    qrKey = kd.data?.unikey || kd.unikey;
    if (!qrKey) { $('qrLoading').textContent = '獲取二維碼失敗'; return; }
    const cd = await api('/api/login/qr/create', { key: qrKey, qrimg: true });
    const img = cd.data?.qrimg || cd.qrimg;
    if (img) {
      const el = $('qrImg');
      const box = el.parentElement;
      box.style.backgroundImage = `url("${img}")`;
      box.style.backgroundSize = 'contain';
      box.style.backgroundRepeat = 'no-repeat';
      box.style.backgroundPosition = 'center';
      el.src = img;
      el.onload = () => { $('qrLoading').style.display = 'none'; };
      el.onerror = () => { $('qrLoading').textContent = '圖片載入失敗'; };
      setTimeout(() => { $('qrLoading').style.display = 'none'; }, 1000);
      $('qrImg').style.display = '';
    } else { $('qrLoading').textContent = '二維碼為空'; }
    startQRPolling();
  } catch(e) { $('qrLoading').textContent = '載入失敗'; }
}
function startQRPolling() {
  stopQRPolling();
  qrTimer = setInterval(async () => {
    if (!qrKey) return;
    try {
      const d = await api('/api/login/qr/check', { key: qrKey });
      const code = d.code;
      if (code === 803) {
        stopQRPolling();
        toast('登入成功 🎉'); closeLogin();
        setTimeout(async () => {
          try { await fetchUserInfo(); } catch {}
          if (!state.user) toast('登入成功，請稍後刷新頁面');
        }, 800);
      } else if (code === 800) {
        stopQRPolling();
        $('qrRefresh').style.display = '';
        $('qrLoading').textContent = '二維碼已過期'; $('qrLoading').style.display = '';
      }
    } catch {}
  }, 2500);
}
function stopQRPolling() { if (qrTimer) { clearInterval(qrTimer); qrTimer = null; } }
$('qrRefresh')?.addEventListener('click', refreshQR);

async function doPasswordLogin() {
  const phone = $('phoneInput').value.trim(), pwd = $('passwordInput').value;
  if (!/^\d{11}$/.test(phone)) { setLoginMsg('請輸入正確的手機號碼', 'error'); return; }
  if (!pwd) { setLoginMsg('請輸入密碼', 'error'); return; }
  setLoginMsg('登入中...', 'loading');
  try {
    const d = await api('/api/login/cellphone', { phone, password: pwd });
    if (d.code === 200) { toast('登入成功 🎉'); closeLogin(); await fetchUserInfo(); }
    else setLoginMsg(friendlyLoginError(d), 'error');
  } catch(e) { setLoginMsg('網絡錯誤: ' + (e.message || ''), 'error'); }
}
async function doSmsLogin() {
  const phone = $('smsPhoneInput').value.trim(), code = $('codeInput').value.trim();
  if (!/^\d{11}$/.test(phone)) { setLoginMsg('請輸入正確的手機號碼', 'error'); return; }
  if (!/^\d{4,6}$/.test(code)) { setLoginMsg('請輸入正確的驗證碼', 'error'); return; }
  setLoginMsg('登入中...', 'loading');
  try {
    const d = await api('/api/login/cellphone', { phone, captcha: code });
    if (d.code === 200) { toast('登入成功 🎉'); closeLogin(); await fetchUserInfo(); }
    else setLoginMsg(friendlyLoginError(d), 'error');
  } catch(e) { setLoginMsg('網絡錯誤: ' + (e.message || ''), 'error'); }
}
async function sendSmsCode() {
  const phone = $('smsPhoneInput').value.trim();
  if (!/^\d{11}$/.test(phone)) return toast('請輸入正確的手機號碼');
  try {
    const d = await api('/api/captcha/sent', { phone });
    if (d.code === 200) { toast('驗證碼已發送'); startCountdown(); }
    else toast(d.message || '發送失敗');
  } catch { toast('發送失敗'); }
}
function startCountdown() {
  let t = 60; const btn = $('sendCodeBtn'); btn.disabled = true; btn.textContent = `${t}s 後重發`;
  const iv = setInterval(() => {
    t--; if (t <= 0) { clearInterval(iv); btn.disabled = false; btn.textContent = '發送驗證碼'; }
    else btn.textContent = `${t}s 後重發`;
  }, 1000);
}
function setLoginMsg(msg, type = '') { const el = $('loginMsg'); el.textContent = msg; el.className = 'login-msg ' + type; }
function closeLogin() { stopQRPolling(); $('loginModal').classList.remove('show'); }

async function fetchUserInfo() {
  try {
    const d = await api('/api/login/status');
    if (d.code === 200 && d.data?.profile) { state.user = d.data.profile; renderUser(); }
    else { state.user = null; clearUser(); }
  } catch { clearUser(); }
}
function renderUser() {
  const u = state.user;
  const avatar = $('spAvatar'); avatar.innerHTML = '';
  if (u.avatarUrl) { const img = document.createElement('img'); img.src = u.avatarUrl + '?param=200y200'; avatar.appendChild(img); }
  else avatar.textContent = (u.nickname || 'U').charAt(0).toUpperCase();
  $('spName').textContent = u.nickname || '用戶';
  $('spSub').textContent = `等級 Lv.${u.level || 0}`;
  $('sbLoginLabel').textContent = '登出';
}
function clearUser() {
  $('spAvatar').innerHTML = '';
  $('spName').textContent = '未登入';
  $('spSub').textContent = '點擊登入網易雲音樂';
  $('sbLoginLabel').textContent = '登入';
}
async function doLogout() { try { await api('/api/logout'); } catch {} state.user = null; clearUser(); toast('已登出'); }

// ========= 側邊欄選項 =========
function handleLoginClick() {
  if (state.user) { closeSidebar(); doLogout(); }
  else { closeSidebar(); setTimeout(() => $('loginModal').classList.add('show'), 350); }
}
function handleLikedClick() {
  closeSidebar();
  setTimeout(() => {
    const listEl = $('likesList'); const empty = $('likesEmpty');
    if (!state.likedIds.length) {
      empty.style.display = 'block'; listEl.innerHTML = '';
    } else {
      empty.style.display = 'none';
      listEl.innerHTML = state.likedPlaylist.map((s, i) => `
        <li class="song-item" data-idx="${i}">
          <div class="song-num">${i + 1}</div>
          <div class="s-info">
            <div class="s-name">${escapeHtml(s.name)}</div>
            <div class="s-artist">${escapeHtml((s.artists || []).map(a => a.name).join(' / '))}</div>
          </div>
          <button class="s-play">▶</button>
        </li>`).join('');
      listEl.querySelectorAll('.song-item').forEach(el => {
        el.addEventListener('click', () => {
          state.playlist = state.likedPlaylist; state.currentIndex = parseInt(el.dataset.idx);
          playSong(state.currentIndex);
        });
      });
    }
    $('likesPage').classList.add('show');
  }, 350);
}
function handleQueueClick() {
  closeSidebar();
  setTimeout(() => {
    if (state.currentIndex < 0) { toast('先播放一首歌曲吧'); return; }
    $('playerPage').classList.add('show');
  }, 350);
}
function handleSettingsClick() {
  closeSidebar();
  setTimeout(() => { syncSettingsUI(); $('settingsModal').classList.add('show'); }, 350);
}

// ========= 設定：背景 + 播放器漸層 =========
function loadBgSettings() {
  try { state.bgSettings = JSON.parse(localStorage.getItem('folia_bg') || 'null'); } catch { state.bgSettings = null; }
  if (!state.bgSettings) state.bgSettings = { color: '#0a0a0c', image: '', opacity: 0.5, blur: 40 };
  try { state.playerGradient = JSON.parse(localStorage.getItem('folia_pg') || 'null'); } catch { state.playerGradient = null; }
  if (!state.playerGradient) state.playerGradient = { color1: '#0f0f14', color2: '#1a0a1a', angle: 180 };
  state.likedIds = JSON.parse(localStorage.getItem('folia_liked') || '[]');
  try { state.loopMode = localStorage.getItem('folia_loop') || 'all'; } catch { state.loopMode = 'all'; }
  setLoopMode(state.loopMode);
  applyBgSettings(); applyPlayerGradient();
  syncSettingsUI();
  buildLikedPlaylist();
}
function applyBgSettings() {
  const s = state.bgSettings;
  document.documentElement.style.setProperty('--custom-bg-color', s.color || '#0a0a0c');
  document.documentElement.style.setProperty('--custom-bg-image', s.image ? `url(${s.image})` : 'none');
  document.documentElement.style.setProperty('--custom-bg-overlay', s.opacity ?? 0.5);
  document.documentElement.style.setProperty('--custom-bg-blur', (s.blur ?? 40) + 'px');
  const pv = $('bgPreview');
  if (pv) {
    if (s.image) { pv.style.backgroundImage = `url(${s.image})`; pv.style.backgroundSize = 'cover'; }
    else { pv.style.backgroundImage = 'none'; pv.style.background = s.color || '#222'; }
  }
}
function applyPlayerGradient() {
  const g = state.playerGradient;
  const val = `linear-gradient(${g.angle}deg, ${g.color1}, ${g.color2})`;
  document.documentElement.style.setProperty('--pg-gradient', val);
  const pv = $('pgPreview');
  if (pv) pv.style.background = val;
}
function buildLikedPlaylist() {
  state.likedPlaylist = state.playlist.filter(s => state.likedIds.includes(s.id));
  if (state.likedIds.length && state.likedPlaylist.length < Math.min(state.likedIds.length, 5)) {
    // 如果當前 playlist 沒有全部喜歡歌曲，保留當前的 + 標記
  }
}
function syncSettingsUI() {
  const s = state.bgSettings || { color: '#0a0a0c', image: '', opacity: 0.5, blur: 40 };
  $('bgColorPicker').value = s.color || '#0a0a0c';
  $('bgOpacity').value = (s.opacity ?? 0.5) * 100;
  $('bgOpacityLabel').textContent = Math.round((s.opacity ?? 0.5) * 100) + '%';
  $('bgBlur').value = s.blur ?? 40;
  $('bgBlurLabel').textContent = (s.blur ?? 40) + 'px';
  $$('.pc-btn').forEach(b => b.style.outline = s.color === b.dataset.c ? '2px solid #fff' : 'none');
  applyBgSettings();

  const g = state.playerGradient || { color1: '#0f0f14', color2: '#1a0a1a', angle: 180 };
  $('pgColor1').value = g.color1;
  $('pgColor2').value = g.color2;
  $('pgAngle').value = g.angle;
  $('pgAngleLabel').textContent = g.angle + '°';
  applyPlayerGradient();
}
function saveBgSettings() {
  try {
    localStorage.setItem('folia_bg', JSON.stringify(state.bgSettings));
    localStorage.setItem('folia_pg', JSON.stringify(state.playerGradient));
    toast('設定已儲存');
  } catch { toast('儲存失敗'); }
}

// ========= 事件綁定 =========
function bindEvents() {
  updateClock(); setInterval(updateClock, 60000);
  setupProgressBar();

  // 漢堡按鈕
  $$('#hamburgerBtn, #hamburgerBtn2').forEach(btn => btn.addEventListener('click', (e) => { e.stopPropagation(); state.sidebarOpen ? closeSidebar() : openSidebar(); }));
  $('sidebarMask').addEventListener('click', closeSidebar);

  // 側邊欄選項
  $('sbLogin').addEventListener('click', () => { closeSidebar(); setTimeout(handleLoginClick, 300); });
  $('sbLiked').addEventListener('click', () => { closeSidebar(); setTimeout(handleLikedClick, 300); });
  $('sbPlaying').addEventListener('click', () => { closeSidebar(); setTimeout(handleQueueClick, 300); });
  $('sbSettings').addEventListener('click', () => { closeSidebar(); setTimeout(handleSettingsClick, 300); });

  // 返回按鈕
  const backMap = { likesBack: 'likesPage', queueBack: 'queuePage' };
  Object.entries(backMap).forEach(([btnId, pageId]) => {
    const btn = $(btnId); if (btn) btn.addEventListener('click', () => $(pageId).classList.remove('show'));
  });

  // Tab 切換
  $$('.tab-item').forEach(t => t.addEventListener('click', () => switchPage(t.dataset.page)));

  // 無限滾動
  $('discoverScroll').addEventListener('scroll', (e) => {
    const el = e.target;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 100) loadWall(false);
  });

  // 搜尋
  const searchInput = $('searchInput');
  searchInput.addEventListener('input', (e) => {
    $('searchClear').style.display = e.target.value ? 'block' : 'none';
    if (!e.target.value.trim()) { $('searchSuggest').innerHTML = ''; $('searchResult').style.display = 'none'; return; }
    showSuggestions(e.target.value);
  });
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { $('searchSuggest').innerHTML = ''; doSearch(e.target.value.trim(), true); }
  });
  $('searchGo').addEventListener('click', () => { if (searchInput.value.trim()) { $('searchSuggest').innerHTML = ''; doSearch(searchInput.value.trim(), true); } });
  $('searchClear').addEventListener('click', () => {
    searchInput.value = ''; $('searchClear').style.display = 'none'; $('searchResult').style.display = 'none'; $('searchSuggest').innerHTML = '';
  });
  $('songList').addEventListener('click', (e) => {
    const item = e.target.closest('.song-item'); if (item) playSong(parseInt(item.dataset.idx));
  });
  $('searchMore').addEventListener('click', () => doSearch(state.searchKeyword, false));

  // 播放器
  $('miniPlayer').addEventListener('click', (e) => {
    if (e.target.closest('.mp-ctrl')) return;
    if (state.playlist.length) $('playerPage').classList.add('show');
  });
  $('playerBack').addEventListener('click', () => $('playerPage').classList.remove('show'));
  $('plBack').addEventListener('click', () => $('playlistPage').classList.remove('show'));
  $('favoriteBtn').addEventListener('click', toggleFavorite);
  $('modeBtn').addEventListener('click', () => {
    const modes = ['all', 'one', 'shuffle'];
    const i = modes.indexOf(state.loopMode);
    setLoopMode(modes[(i + 1) % modes.length]);
    const labels = { all: '列表循環', one: '單曲循環', shuffle: '隨機播放' };
    toast(labels[state.loopMode]);
  });
  $('queueBtn').addEventListener('click', () => { renderQueue(); $('queuePage').classList.add('show'); $('playerPage').classList.remove('show'); });
  $('mpPlayBtn').addEventListener('click', togglePlay);
  $('playBtn').addEventListener('click', togglePlay);
  $('prevBtn').addEventListener('click', prevTrack);
  $('nextBtn').addEventListener('click', nextTrack);

  // Audio 事件
  audio.addEventListener('ended', () => {
    if (state.loopMode === 'one' && state.currentIndex >= 0) playSong(state.currentIndex);
    else nextTrack();
  });
  audio.addEventListener('pause', () => {
    updatePlayPauseIcon(false);
    $('mpCover').classList.remove('playing'); $('coverDisc').classList.remove('playing');
    state.isPlaying = false; stopProgressTimer();
  });
  audio.addEventListener('play', () => {
    updatePlayPauseIcon(true);
    $('mpCover').classList.add('playing'); $('coverDisc').classList.add('playing');
    state.isPlaying = true; startProgressTimer();
  });
  audio.addEventListener('error', () => { toast('播放失敗'); state.isPlaying = false; });

  // 登入
  $('loginClose').addEventListener('click', closeLogin);
  $('loginModal').addEventListener('click', (e) => { if (e.target === $('loginModal')) closeLogin(); });
  $$('.ltab').forEach(t => t.addEventListener('click', () => {
    $$('.ltab').forEach(x => x.classList.remove('active')); t.classList.add('active');
    const tab = t.dataset.tab;
    $('pwdForm').style.display = tab === 'pwd' ? '' : 'none';
    $('smsForm').style.display = tab === 'sms' ? '' : 'none';
    $('qrForm').style.display = tab === 'qr' ? '' : 'none';
    setLoginMsg('');
    if (tab === 'qr') refreshQR(); else stopQRPolling();
  }));
  $('pwdForm').addEventListener('submit', (e) => { e.preventDefault(); doPasswordLogin(); });
  $('smsForm').addEventListener('submit', (e) => { e.preventDefault(); doSmsLogin(); });
  $('sendCodeBtn').addEventListener('click', sendSmsCode);

  // 設定
  $('settingsClose').addEventListener('click', () => $('settingsModal').classList.remove('show'));
  $('settingsModal').addEventListener('click', (e) => { if (e.target === $('settingsModal')) $('settingsModal').classList.remove('show'); });
  $('bgColorPicker').addEventListener('input', (e) => { state.bgSettings.color = e.target.value; syncSettingsUI(); });
  $$('.pc-btn').forEach(b => b.addEventListener('click', () => { state.bgSettings.color = b.dataset.c; syncSettingsUI(); }));
  $('bgImageInput').addEventListener('change', (e) => {
    const f = e.target.files[0]; if (!f) return;
    const reader = new FileReader();
    reader.onload = () => { state.bgSettings.image = reader.result; syncSettingsUI(); };
    reader.readAsDataURL(f);
  });
  $('bgImageUrl').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.value.trim()) { state.bgSettings.image = e.target.value.trim(); syncSettingsUI(); toast('已套用圖片'); }
  });
  $('clearBgBtn').addEventListener('click', () => { state.bgSettings.image = ''; $('bgImageUrl').value = ''; syncSettingsUI(); toast('已清除背景圖片'); });
  $('bgOpacity').addEventListener('input', (e) => { state.bgSettings.opacity = e.target.value / 100; syncSettingsUI(); });
  $('bgBlur').addEventListener('input', (e) => { state.bgSettings.blur = parseInt(e.target.value); syncSettingsUI(); });
  // 播放器漸層
  $('pgColor1').addEventListener('input', (e) => { state.playerGradient.color1 = e.target.value; applyPlayerGradient(); $('pgAngleLabel').textContent = state.playerGradient.angle + '°'; });
  $('pgColor2').addEventListener('input', (e) => { state.playerGradient.color2 = e.target.value; applyPlayerGradient(); });
  $('pgAngle').addEventListener('input', (e) => { state.playerGradient.angle = parseInt(e.target.value); applyPlayerGradient(); $('pgAngleLabel').textContent = state.playerGradient.angle + '°'; });
  $$('.pg-presets .pc-btn').forEach(b => b.addEventListener('click', () => {
    const preset = b.dataset.preset;
    const map = {
      dark: ['#0f0f14', '#1a0a1a', 180],
      sunset: ['#2a0a0f', '#3d0f2a', 180],
      ocean: ['#0a1a2a', '#0a2a3d', 180],
      forest: ['#0a2a1a', '#0a3d1a', 180],
      void: ['#141421', '#2a0a3d', 180],
    };
    const [c1, c2, ang] = map[preset];
    state.playerGradient = { color1: c1, color2: c2, angle: ang };
    syncSettingsUI();
  }));
  $('saveSettingsBtn').addEventListener('click', () => { saveBgSettings(); $('settingsModal').classList.remove('show'); });

  // ESC
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closeSidebar(); $$('.login-modal.show').forEach(m => m.classList.remove('show')); }
  });
}

// ========= 啟動 =========
async function init() {
  bindEvents();
  loadBgSettings();
  loadWall(true);
  initSearchFresh();
  try { await fetchUserInfo(); } catch {}
  // 恢復上次播放狀態
  if (!restoreLastState()) {
    // 第一次使用：顯示預設狀態
    updatePlayerUI(null);
  }
}

init().catch(e => { console.error('init:', e); toast('啟動失敗: ' + e.message); });
