const fs = require('fs');
const path = require('path');
const tmp = process.env.TEMP;
const dstDir = path.join(__dirname, 'public');

['icon-192.png', 'icon-512.png'].forEach(f => {
  const s = path.join(tmp, 'folia-icons', f);
  const t = path.join(dstDir, f);
  if (fs.existsSync(s)) {
    fs.copyFileSync(s, t);
    console.log('✅ copied:', f, fs.statSync(t).size + 'B');
  } else {
    console.log('❌ missing:', s);
  }
});

// Verify
console.log('\nVerification:');
['icon-192.png', 'icon-512.png'].forEach(f => {
  const p = path.join(dstDir, f);
  console.log(f, fs.existsSync(p) ? '✅' : '❌', fs.existsSync(p) ? fs.statSync(p).size + 'B' : '');
});
