/* ═══════════════════════════════════════════════════════════
   Majestic Market — Enhanced JS v2
   ═══════════════════════════════════════════════════════════ */

// ── Toast notifications ───────────────────────────────────────
const ToastIcons = {success:'✅',danger:'❌',warning:'⚠️',info:'ℹ️'};
function showToast(msg, type='success', duration=3800){
  let c = document.getElementById('toast-container');
  if(!c){ c=document.createElement('div'); c.id='toast-container'; document.body.appendChild(c); }
  const t = document.createElement('div');
  t.className='toast-item';
  t.innerHTML=`<span style="font-size:1rem">${ToastIcons[type]||'✦'}</span><span>${msg}</span>`;
  if(type==='success') t.style.borderLeft='3px solid #22c55e';
  else if(type==='danger')  t.style.borderLeft='3px solid #ef4444';
  else if(type==='warning') t.style.borderLeft='3px solid #f59e0b';
  c.appendChild(t);
  setTimeout(()=>{t.style.transition='opacity .4s'; t.style.opacity='0'; setTimeout(()=>t.remove(),400);}, duration);
}

// ── DOM Ready ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded',()=>{

  // Page fade-in
  document.body.classList.add('page-fade');

  // Auto-dismiss alerts → toast
  document.querySelectorAll('.alert').forEach(el=>{
    const txt = el.querySelector('.alert-msg')?.textContent || el.textContent.replace('×','').trim();
    const type = el.classList.contains('alert-success')?'success':
                 el.classList.contains('alert-danger')?'danger':
                 el.classList.contains('alert-warning')?'warning':'info';
    showToast(txt.slice(0,120), type);
    el.style.display='none';
  });

  // Back-to-top
  const btn = document.getElementById('back-top');
  if(btn){
    window.addEventListener('scroll',()=>{
      btn.classList.toggle('show', window.scrollY>300);
    });
    btn.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));
  }

  // Card entrance animations
  if('IntersectionObserver' in window){
    const obs = new IntersectionObserver(entries=>{
      entries.forEach(e=>{
        if(e.isIntersecting){
          e.target.style.opacity='1';
          e.target.style.transform='translateY(0)';
          obs.unobserve(e.target);
        }
      });
    },{threshold:0.08});
    document.querySelectorAll('.product-card,.glass-card,.stat-card,.cat-card').forEach(el=>{
      el.style.opacity='0';
      el.style.transform='translateY(18px)';
      el.style.transition='opacity .5s ease,transform .5s ease';
      obs.observe(el);
    });
  }

  // Image upload preview
  const imgIn = document.getElementById('imageInput');
  const imgPrev = document.getElementById('imagePreview');
  if(imgIn && imgPrev){
    imgIn.addEventListener('change',function(){
      const f = this.files[0];
      if(f){
        const r = new FileReader();
        r.onload = e=>{ imgPrev.src=e.target.result; imgPrev.style.display='block'; };
        r.readAsDataURL(f);
      }
    });
  }

  // Character counter
  const descEl = document.getElementById('descriptionField');
  const cntEl  = document.getElementById('descCount');
  if(descEl && cntEl){
    const update = ()=>{ cntEl.textContent=descEl.value.length; };
    descEl.addEventListener('input', update); update();
  }

  // Price format
  document.querySelectorAll('.price-input').forEach(el=>{
    el.addEventListener('blur',function(){ if(this.value&&!isNaN(this.value)) this.value=parseFloat(this.value).toFixed(2); });
  });

  // Confirm delete
  document.querySelectorAll('.confirm-delete').forEach(btn=>{
    btn.addEventListener('click',e=>{ if(!confirm(btn.dataset.confirm||'Are you sure?')) e.preventDefault(); });
  });

  // Chat scroll
  document.querySelectorAll('.chat-window,.ai-window').forEach(el=>{ el.scrollTop=el.scrollHeight; });

  // Category pills: sync with select
  document.querySelectorAll('.cat-pill[data-cat]').forEach(pill=>{
    pill.addEventListener('click',function(){
      const url = new URL(window.location.href);
      url.searchParams.set('category', this.dataset.cat);
      window.location.href = url.toString();
    });
  });

  // Admin tabs
  document.querySelectorAll('.admin-tab').forEach(tab=>{
    tab.addEventListener('click',function(){
      document.querySelectorAll('.admin-tab').forEach(t=>t.classList.remove('active'));
      document.querySelectorAll('.admin-pane').forEach(p=>p.style.display='none');
      this.classList.add('active');
      const target = document.getElementById(this.dataset.target);
      if(target) target.style.display='block';
    });
  });

  // Admin search filter (client-side)
  const adminSearch = document.getElementById('adminSearch');
  if(adminSearch){
    adminSearch.addEventListener('input',function(){
      const q = this.value.toLowerCase();
      document.querySelectorAll('.admin-row').forEach(row=>{
        row.style.display = row.textContent.toLowerCase().includes(q)?'':'none';
      });
    });
  }

  // Favorite AJAX
  document.querySelectorAll('.fav-btn').forEach(btn=>{
    btn.addEventListener('click',async function(e){
      e.preventDefault();
      const pid = this.dataset.pid;
      const res = await fetch(`/favorite/${pid}`,{
        method:'POST',
        headers:{'X-Requested-With':'XMLHttpRequest','Content-Type':'application/json'}
      });
      const data = await res.json();
      if(data.action==='added'){
        this.innerHTML='<i class="bi bi-heart-fill"></i>';
        this.style.color='#fca5a5';
        showToast('Added to wishlist','success');
      } else {
        this.innerHTML='<i class="bi bi-heart"></i>';
        this.style.color='';
        showToast('Removed from wishlist','info');
      }
    });
  });

  // Build category chart (admin)
  buildCatChart();

  // Init AI chat
  initAIChat();

  // Init message polling
  initMessagePolling();

});

// ── Category bar chart ─────────────────────────────────────────
function buildCatChart(){
  const container = document.getElementById('catChart');
  if(!container) return;
  const bars = container.querySelectorAll('.chart-bar');
  const maxVal = Math.max(...[...bars].map(b=>parseInt(b.dataset.value)||0), 1);
  bars.forEach(bar=>{
    const val = parseInt(bar.dataset.value)||0;
    const pct = Math.max((val/maxVal)*100, 4);
    setTimeout(()=>{ bar.style.height=pct+'%'; }, 100);
    bar.setAttribute('data-label', `${bar.dataset.name}: ${val}`);
  });
}

// ── AI Chat ───────────────────────────────────────────────────
function initAIChat(){
  const form  = document.getElementById('aiChatForm');
  const input = document.getElementById('aiInput');
  const cont  = document.getElementById('aiChatContainer');
  if(!form||!input||!cont) return;

  form.addEventListener('submit', async e=>{
    e.preventDefault();
    const msg = input.value.trim(); if(!msg) return;
    appendAIBubble(cont, msg, 'user');
    input.value=''; input.focus();
    const tid = showTypingAI(cont);
    try{
      const res = await fetch('/ai-chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})});
      const data = await res.json();
      removeTyping(tid); appendAIBubble(cont, data.reply, 'bot');
    } catch{
      removeTyping(tid); appendAIBubble(cont,'Connection error. Please try again.','bot');
    }
  });
}

function appendAIBubble(c, text, role){
  const wrap = document.createElement('div');
  wrap.className=`d-flex align-items-end mb-3 ${role==='user'?'justify-content-end':'gap-2'}`;
  if(role==='bot'){
    const av=document.createElement('div'); av.className='ai-avatar'; av.textContent='✦';
    wrap.appendChild(av);
  }
  const b=document.createElement('div'); b.className=`ai-bubble ${role}`;
  b.innerHTML=text; wrap.appendChild(b);
  c.appendChild(wrap); c.scrollTop=c.scrollHeight;
}
function showTypingAI(c){
  const id='typing-'+Date.now();
  const w=document.createElement('div');
  w.id=id; w.className='d-flex align-items-end mb-3 gap-2';
  w.innerHTML=`<div class="ai-avatar">✦</div>
    <div class="ai-bubble bot"><div class="typing-dots">
      <span></span><span></span><span></span></div></div>`;
  c.appendChild(w); c.scrollTop=c.scrollHeight; return id;
}
function removeTyping(id){ const e=document.getElementById(id); if(e) e.remove(); }
function sendChip(t){ const i=document.getElementById('aiInput'); if(i){i.value=t; document.getElementById('aiChatForm').dispatchEvent(new Event('submit')); } }

// ── Message Polling ───────────────────────────────────────────
function initMessagePolling(){
  const chatWin = document.getElementById('chatWindow');
  const otherId = document.getElementById('otherUserId');
  if(!chatWin||!otherId) return;

  let lastTime = chatWin.dataset.lastTime || '2000-01-01 00:00:00';

  async function poll(){
    try{
      const res  = await fetch(`/messages/poll/${otherId.value}?since=${encodeURIComponent(lastTime)}`);
      const data = await res.json();
      if(data.msgs && data.msgs.length>0){
        const uid = parseInt(document.getElementById('currentUserId')?.value||0);
        data.msgs.forEach(m=>{
          appendChatBubble(chatWin, m, uid);
          lastTime = m.created_at;
        });
        chatWin.scrollTop = chatWin.scrollHeight;
        showToast('New message received','info');
      }
    } catch(e){ /* silent */ }
  }

  setInterval(poll, 5000); // poll every 5 seconds
}

function appendChatBubble(win, m, uid){
  const isSent = m.sender_id===uid;
  const wrap = document.createElement('div');
  wrap.className=`d-flex ${isSent?'justify-content-end':''}`;
  wrap.style.marginBottom='.75rem';
  const b=document.createElement('div');
  b.className=`chat-bubble ${isSent?'sent':'recv'}`;
  b.innerHTML=`${isSent?'':
    `<div class="chat-sender">${m.sname||'User'}</div>`}
    ${m.content}
    <span class="chat-meta">${(m.created_at||'').slice(11,16)}</span>`;
  wrap.appendChild(b); win.appendChild(wrap);
}
