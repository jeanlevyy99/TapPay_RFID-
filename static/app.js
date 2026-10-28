const products = window.PRODUCTS || [];
const cart = new Map();
let category = 'All products';
let latestStatus = {};
let lastSeenUid = '';
let toastTimer;
const $ = id => document.getElementById(id);
const money = n => '₹' + Number(n).toLocaleString('en-IN');

function toast(message, type='info') {
  const el = $('toast'); el.textContent = message; el.className = 'toast ' + type;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.add('hidden'), 5000);
}
function categories() {
  const names = ['All products', ...new Set(products.map(p => p.category))];
  $('categories').innerHTML = names.map(n => `<button class="category-btn ${n===category?'active':''}" data-category="${n}">${n}</button>`).join('');
  $('categories').querySelectorAll('button').forEach(b => b.onclick = () => { category = b.dataset.category; categories(); renderProducts(); });
}
function renderProducts() {
  const list = category === 'All products' ? products : products.filter(p => p.category === category);
  $('products').innerHTML = list.map(p => `<article class="product-card"><img src="${p.image}" alt="${p.name}" loading="lazy" onerror="this.src='https://placehold.co/500x350/e8eee8/245b43?text=Product'"><div class="product-info"><div class="product-category">${p.category}</div><div class="product-name" title="${p.name}">${p.name}</div><div class="product-bottom"><span class="product-price">${money(p.price)}</span><button class="add-btn" data-add="${p.id}" aria-label="Add ${p.name}">+</button></div></div></article>`).join('');
  $('products').querySelectorAll('[data-add]').forEach(b => b.onclick = () => { const id=b.dataset.add; cart.set(id,(cart.get(id)||0)+1); renderCart(); });
}
function renderCart() {
  const items = [...cart.entries()];
  const count = items.reduce((n,[,q])=>n+q,0);
  const total = items.reduce((n,[id,q])=>n+products.find(p=>p.id===id).price*q,0);
  $('cartCount').textContent = count; $('cartTotal').textContent = money(total); $('checkoutBtn').disabled = !count;
  if (!items.length) {
    $('cartItems').innerHTML = '<div class="empty-state"><div class="empty-icon">＋</div><strong>Your cart is empty</strong><span>Add a product to get started.</span></div>';
    return;
  }
  $('cartItems').innerHTML = items.map(([id,q])=>{const p=products.find(x=>x.id===id);return `<div class="cart-row"><div><div class="cart-row-name">${p.name}</div><div class="cart-row-sub">${money(p.price)} each</div></div><div class="cart-row-right"><div class="cart-row-price">${money(p.price*q)}</div><div class="qty-control"><button data-minus="${id}" aria-label="Decrease">−</button><span>${q}</span><button data-plus="${id}" aria-label="Increase">+</button></div></div></div>`}).join('');
  $('cartItems').querySelectorAll('[data-minus]').forEach(b=>b.onclick=()=>{let q=cart.get(b.dataset.minus)-1;if(q<=0)cart.delete(b.dataset.minus);else cart.set(b.dataset.minus,q);renderCart();});
  $('cartItems').querySelectorAll('[data-plus]').forEach(b=>b.onclick=()=>{let id=b.dataset.plus;cart.set(id,Math.min(99,(cart.get(id)||0)+1));renderCart();});
}
async function api(url, options={}) {
  const res = await fetch(url,{headers:{'Content-Type':'application/json'},...options});
  let data; try { data=await res.json(); } catch { data={error:'Unexpected server response.'}; }
  if(!res.ok) throw new Error(data.error || 'Request failed.');
  return data;
}
async function refreshStatus() {
  try {
    const s=await api('/api/status'); latestStatus=s;
    const pill=$('connectionPill');
    pill.className='pill '+(s.connected?'connected':'muted');
    pill.querySelector('span').textContent=s.connected?`Arduino connected · ${s.port}`:'Arduino disconnected';
    $('connectBtn').textContent=s.connected?'Connected ✓':'Connect Arduino ↗';
    $('connectBtn').disabled=s.connected;
    if(s.last_uid && s.last_uid!==lastSeenUid) {
      lastSeenUid=s.last_uid;
      toast(`Card detected: ${s.last_uid}`,'success');
    }
    if(s.last_uid) $('pendingUid').textContent=s.last_uid;
    $('scanTitle').textContent=s.student ? `Hello, ${s.student.name}` : (s.last_uid ? 'Card detected' : (s.connected?'Ready to scan':'Waiting for card'));
    $('scanMessage').textContent=s.student ? `Card ${s.student.uid} is registered. Balance: ${money(s.student.balance)}.` : (s.last_uid ? `UID ${s.last_uid}. ${s.connected?'Register it in the administrator panel if it is new.':'Connect Arduino to read cards.'}` : (s.connected?'Tap a compatible RFID card on the reader.':'Connect your Arduino, then tap a compatible RFID card.'));
    if(s.student){ $('activeStudent').classList.remove('hidden'); $('activeStudent').innerHTML=`<strong>${escapeHtml(s.student.name)}</strong><span>Card UID · ${escapeHtml(s.student.uid)}</span><div class="balance">${money(s.student.balance)}</div><span>Available simulated balance</span>`; }
    else $('activeStudent').classList.add('hidden');
    if(s.result==='approved') $('scanTitle').textContent='Payment approved';
    if(s.result==='declined') $('scanTitle').textContent='Payment declined';
  } catch(e) { /* server may still be starting */ }
}
function escapeHtml(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function loadPorts() {
  try {
    const d=await api('/api/ports'); const select=$('portSelect'); const old=select.value;
    select.innerHTML='<option value="">Choose a serial port…</option>'+d.ports.map(p=>`<option value="${escapeHtml(p.device)}">${escapeHtml(p.device)} — ${escapeHtml(p.description||'Serial device')}</option>`).join('');
    if(old) select.value=old;
    if(!d.ports.length) toast('No serial ports detected. Check the USB cable and driver, or enter the port manually.','info');
  } catch(e){toast(e.message,'error');}
}
$('refreshPorts').onclick=loadPorts;
$('connectBtn').onclick=async()=>{
  const port=$('manualPort').value.trim()||$('portSelect').value;
  if(!port){toast('Select a serial port or enter it manually (for example COM3).','error');return;}
  try{const d=await api('/api/connect',{method:'POST',body:JSON.stringify({port})});toast(d.message,'info');setTimeout(refreshStatus,500);}catch(e){toast(e.message,'error');}
};
$('clearCart').onclick=()=>{cart.clear();renderCart();};
$('checkoutBtn').onclick=async()=>{
  const items=[...cart.entries()].map(([id,qty])=>({id,qty}));
  if(!items.length)return;
  if(!latestStatus.last_uid || Date.now()/1000-latestStatus.last_scan_at>180){toast('Tap your physical RFID card first.','error');return;}
  const total=items.reduce((sum,i)=>sum+products.find(p=>p.id===i.id).price*i.qty,0);
  const name=latestStatus.student?.name || 'unregistered card';
  if(!confirm(`Charge ${money(total)} to ${name}?\n\nThis is a simulated payment only. Tap the card first if the card changes.`))return;
  try{const d=await api('/api/pay',{method:'POST',body:JSON.stringify({items})});cart.clear();renderCart();toast(`${d.message} Remaining balance: ${money(d.student.balance)}.`,'success');await refreshStatus();await loadTransactions();await loadStudents();}
  catch(e){toast(e.message,'error');await refreshStatus();}
};
$('openAdmin').onclick=()=>{ $('adminPanel').classList.add('open'); $('adminPanel').scrollIntoView({behavior:'smooth',block:'start'}); };
$('closeAdmin').onclick=()=> $('adminPanel').classList.remove('open');
$('registerForm').onsubmit=async e=>{
  e.preventDefault(); const feedback=$('registerFeedback'); feedback.className='feedback hidden';
  try{
    const d=await api('/api/register',{method:'POST',body:JSON.stringify({name:$('studentName').value,balance:$('initialBalance').value})});
    feedback.textContent=`Registered ${d.student.name} · UID ${d.student.uid} · Starting balance ${money(d.student.balance)}.`;feedback.className='feedback success';
    $('studentName').value='';toast('Student card registered successfully.','success');await loadStudents();await refreshStatus();
  }catch(err){feedback.textContent=err.message;feedback.className='feedback error';toast(err.message,'error');}
};
async function loadStudents(){
  try{const d=await api('/api/students');$('studentsTable').innerHTML=d.students.length?d.students.map(s=>`<tr><td><strong>${escapeHtml(s.name)}</strong></td><td><code>${escapeHtml(s.uid)}</code></td><td>${money(s.initial_balance)}</td><td><strong>${money(s.balance)}</strong></td></tr>`).join(''):'<tr><td colspan="4" class="table-empty">No students registered yet.</td></tr>';}
  catch(e){toast(e.message,'error');}
}
async function loadTransactions(){
  try{const d=await api('/api/transactions');$('transactionsTable').innerHTML=d.transactions.length?d.transactions.map(t=>`<tr><td>#${t.id}</td><td>${escapeHtml(t.student_name)}</td><td><strong>${money(t.total)}</strong></td><td>${money(t.balance_after)}</td><td>${escapeHtml(t.created_at)}</td></tr>`).join(''):'<tr><td colspan="5" class="table-empty">No transactions yet.</td></tr>';}
  catch(e){toast(e.message,'error');}
}
$('reloadStudents').onclick=loadStudents;$('reloadTransactions').onclick=loadTransactions;
categories();renderProducts();renderCart();loadPorts();loadStudents();loadTransactions();refreshStatus();setInterval(refreshStatus,1200);
