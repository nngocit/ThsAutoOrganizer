// cloudflare/pages/scripts/build.js — Build tĩnh: copy src/** → dist/ (Node thuần, không bundler)
// Bỏ qua node_modules, .wrangler, dist, .git nếu lỡ nằm trong vùng copy.
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'src');
const DIST = path.join(ROOT, 'dist');
const EXCLUDE = new Set(['node_modules', '.wrangler', 'dist', '.git']);

let copiedCount = 0;

function copyRecursive(srcPath, destPath) {
  const stat = fs.statSync(srcPath);
  if (stat.isDirectory()) {
    if (EXCLUDE.has(path.basename(srcPath))) return;
    fs.mkdirSync(destPath, { recursive: true });
    for (const entry of fs.readdirSync(srcPath)) {
      copyRecursive(path.join(srcPath, entry), path.join(destPath, entry));
    }
  } else {
    fs.mkdirSync(path.dirname(destPath), { recursive: true });
    fs.copyFileSync(srcPath, destPath);
    copiedCount++;
  }
}

function main() {
  if (!fs.existsSync(SRC)) {
    console.error(`[build] Không tìm thấy thư mục src: ${SRC}`);
    process.exit(1);
  }
  // Xoá dist cũ rồi copy sạch
  fs.rmSync(DIST, { recursive: true, force: true });
  copyRecursive(SRC, DIST);
  console.log(`[build] OK — đã copy ${copiedCount} file từ src/ → dist/`);
  console.log('[build] Deploy: npx wrangler pages deploy dist --project-name=ths-organizer');
}

main();
