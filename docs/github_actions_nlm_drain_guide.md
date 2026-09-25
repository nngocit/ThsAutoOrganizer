# Hướng Dẫn PA2 — Nạp NotebookLM Bằng GitHub Actions (không cần PC ở nhà)

> **Mục đích:** khi bạn ở ngoài (4G) upload tài liệu lên Drive, GitHub sẽ chạy `nlm` trên một máy ảo Linux tạm (thay PC ở nhà) để đẩy tài liệu vào đúng sổ NotebookLM.
> **Repo:** `nngocit/ThsAutoOrganizer` (PRIVATE) → runner **2 vCPU / 7 GB RAM / 14 GB SSD**, dùng **2.000 phút/tháng** (Free plan).
> **File liên quan:** `.github/workflows/nlm-drain.yml` · `local_agent/drain_once.py` · `local_agent/firestore_poller.py` (`run_once`, `run_until_idle`)

---

## 1. Kiến trúc

```
📱 Mobile 4G ──upload──► Cloudflare Worker ──► Google Drive + Firestore (file status=pending)
                                                     + nlm_task_queue/{taskId} status=pending
                                                     │
                                    (bạn bấm Run / Worker dispatch / cron 15')
                                                     ▼
🤖 GitHub Actions runner (máy tạm, IP datacenter)
   auth.json (từ Secret) → `nlm notebook list` (smoke test)
   → `python -m local_agent.drain_once`
   → tải PDF từ Drive → `nlm source add <notebook_id> --file … --wait`
   → PATCH task = done  → Worker set notebooklm_sync_status='synced'
                                                     ▼
✅ Web UI: badge "🧠 NLM: Đang nạp..." → "🧠 NLM: Đã nạp"
```

Điểm quan trọng: **Cloudflare Worker là phần luôn-bật** (nhận upload, hàng đợi, cron). GitHub runner chỉ là "bàn tay" chạy `nlm` theo sự kiện, sống 2–3 phút rồi bị xoá.

---

## 2. Kích hoạt workflow (1 lần)

1. Push các file mới lên nhánh `main`:
   ```powershell
   git add .github/workflows/nlm-drain.yml local_agent/drain_once.py `
           local_agent/firestore_poller.py tests/test_drain_once.py `
           docs/github_actions_nlm_drain_guide.md
   git commit -m "feat(agent): drain-mode cho GitHub Actions (nap NotebookLM khong can PC)"
   git push origin main
   ```
2. GitHub → repo → **Settings → Actions → General** → chọn *Allow all actions* (nếu đang tắt).
3. Vào tab **Actions** → chọn workflow **NLM Drain** → *Run workflow*.

---

## 3. Tạo Secrets (Settings → Secrets and variables → Actions)

| Secret | Giá trị | Lấy ở đâu |
|---|---|---|
| `WORKER_URL` | `https://ths-organizer-api.ths-organizer-nngocit.workers.dev` | `config.json` |
| `AGENT_SECRET` | (chuỗi 64 ký tự) | `config.json` → `agent_secret` |
| `NOTEBOOKLM_AUTH_B64` | base64 của `auth.json` | xem lệnh dưới |

```powershell
# 1) Mã hoá phiên Google thành base64 (Windows PowerShell) rồi copy vào clipboard
[Convert]::ToBase64String(
  [IO.File]::ReadAllBytes("$env:USERPROFILE\.notebooklm-mcp-cli\profiles\default\auth.json")
) | Set-Clipboard

# 2) Hoặc dùng GitHub CLI (nếu đã cài `gh`)
gh auth login
gh secret set WORKER_URL          --repo nngocit/ThsAutoOrganizer --body "https://ths-organizer-api.ths-organizer-nngocit.workers.dev"
gh secret set AGENT_SECRET        --repo nngocit/ThsAutoOrganizer --body "<agent_secret>"
gh secret set NOTEBOOKLM_AUTH_B64 --repo nngocit/ThsAutoOrganizer --body "$([Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:USERPROFILE\.notebooklm-mcp-cli\profiles\default\auth.json")))"
```

---

## 4. Kiểm tra theo 3 bước (đúng thứ tự)

1. **Dry-run** (không gọi API): Run workflow → `dry_run = true` → log phải in `Dry-run OK: queue=… worker=…`.
2. **Smoke test phiên Google**: Run workflow → `dry_run = false`, `max_passes = 1` → xem step *Smoke test phiên NotebookLM* có xanh (`Phiên NotebookLM OK`) không.
   - Nếu đỏ ⇒ IP datacenter bị Google từ chối, hoặc cookie hết hạn ⇒ xem mục 7.
3. **Nạp thật 1 file**: upload 1 PDF nhỏ từ điện thoại → Run workflow (`max_passes = 30`) → kiểm tra Firestore `notebooklm_sync_status = synced` và badge UI đổi sang **🧠 NLM: Đã nạp**.

---

## 5. Bật chế độ tự động (tùy chọn)

**a) Tự động sau mỗi upload.** Bỏ comment khối `repository_dispatch` trong workflow, rồi thêm vào `cloudflare/workers/src/routes/files/upload.js` (sau bước tạo task):

```js
if (c.env.GITHUB_DISPATCH_TOKEN) {
  c.executionCtx.waitUntil(fetch('https://api.github.com/repos/nngocit/ThsAutoOrganizer/dispatches', {
    method: 'POST',
    headers: { Authorization: `Bearer ${c.env.GITHUB_DISPATCH_TOKEN}`,
               Accept: 'application/vnd.github+json', 'User-Agent': 'ths-organizer' },
    body: JSON.stringify({ event_type: 'nlm-drain', client_payload: { file_id: fileId } }),
  }).catch(() => {}));
}
```

Cần: PAT fine-grained (chỉ repo này; quyền tối thiểu cho endpoint `dispatches` = **Contents: write**) → `wrangler secret put GITHUB_DISPATCH_TOKEN`.

**b) Cron 15 phút.** Bỏ comment khối `schedule`. Lưu ý GitHub: cron ngắn nhất **5 phút**, lịch **có thể trễ**, và workflow `schedule` **tự bị vô hiệu sau 60 ngày repo không có hoạt động**.

---

## 6. Chi phí & hạn mức (repo private)

| Chỉ số | Giá trị |
|---|---|
| Runner | `ubuntu-latest` → 2 vCPU / 7 GB / 14 GB SSD |
| Phút miễn phí | 2.000 phút/tháng (Free plan); mỗi run ~2–3 phút ⇒ ~700–900 run/tháng |
| Vượt quota | Job bị chặn nếu chưa có payment method (theo GitHub docs) |
| Thời lượng job | tối đa 15 phút (đã đặt `timeout-minutes: 15`) |
| Egress | Không tính tiền ⇒ tải file từ Drive rồi đẩy lên NotebookLM miễn phí |
| Lưu trữ | Máy bị xoá sau mỗi run (không giữ file) |

---

## 7. Xử lý sự cố

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `nlm notebook list` báo cần đăng nhập | Cookie hết hạn (vài tuần/lần) | Ở nhà `nlm login` → cập nhật Secret `NOTEBOOKLM_AUTH_B64` |
| Lỗi sign-in/verification dù cookie mới | IP datacenter bị Google từ chối | Thử lại vài lần; nếu luôn lỗi ⇒ PA2 không dùng được với tài khoản này |
| `browser_bound_replay` (khi chạy `nlm doctor auth-replay`) | Cookie chỉ dùng được trong browser thật | PA2 vô hiệu ⇒ chuyển PA1 (Termux) hoặc PA4 (nạp tay trong Web UI) |
| Badge đứng ở "Đang nạp..." nhưng log xanh | Task nằm ngoài 50 doc đầu của queue (`routes/sync/index.js:159-165`) | Bấm "🔄 Nạp lại tệp chờ sync" (route `retry.js`) hoặc xem mục 8 |
| Task kẹt `processing` (job timeout giữa chừng) | `GET /api/tasks` chỉ trả `pending` | Nút retry thủ công; nên bổ sung cron reset stale (mục 8) |
| Nguồn bị nạp trùng trong notebook | 2 run chồng nhau | Đã chặn bằng `concurrency: group: nlm-drain` — không bỏ khối này |
| Workflow tự ngừng chạy sau ~2 tháng | `schedule` bị vô hiệu do repo không hoạt động | Bấm Run lại / dispatch, hoặc commit bất kỳ |
| File không được nhận vào notebook | > 50 MB hoặc > 1000 trang | Chẻ nhỏ tài liệu rồi upload lại |

---

## 8. Hạn chế đã biết (đã xử lý bằng G1 + G2 — xem mục 10 để bật/tắt)

1. ~~`GET /api/tasks/:queue` chỉ trả `pending` trong 50 document đầu~~ → **ĐÃ SỬA (G1)**: mặc định lọc `pending` ngay tại server bằng `runQuery`; có công tắc để quay lại cách cũ.
2. ~~Task kẹt `processing` không bao giờ được nhặt lại~~ → **ĐÃ SỬA (G2)**: task `processing` quá ngưỡng (mặc định 15 phút) tự được trả về `pending`; có công tắc để tắt.
3. `drain_once` **không** xử lý `artifact_download` (cần `googleapiclient` + `token.json`) và `reconcile_local` (cần ổ đĩa PC) — hai việc này vẫn để PC làm.
4. PA2 không phải host luôn-bật: nó chỉ chạy khi được kích hoạt (bấm tay / dispatch / cron).

---

## 9. Bảo mật

- Repo để **private**; không commit `config.json`, `token.json`, `auth.json`.
- Workflow khai báo `permissions: contents: read`, `persist-credentials: false`, action **pin theo SHA**.
- Khi muốn thu hồi quyền: ở nhà chạy `nlm logout` và xoá Secret `NOTEBOOKLM_AUTH_B64` (hoặc đổi mật khẩu Google).
- Không in cookie ra log (workflow chỉ in số byte của `auth.json`).

---

## 10. Công tắc bật/tắt G1 + G2 (Bảo trì hàng đợi)

| Tính năng | Ý nghĩa | Mặc định |
|---|---|---|
| **G1 — `tasks_query_mode`** | `query` = lọc task `pending` **ngay tại server** (chống bỏ sót file khi hàng đợi > 50 task). `legacy` = cách cũ (lấy N doc đầu rồi lọc trong Worker) | `query` |
| **G2 — `tasks_recovery_enabled`** | Tự trả task kẹt `processing` (do PC tắt / job GitHub hết timeout) về `pending` | `true` |
| **G2 — `tasks_stale_minutes`** | Ngưỡng coi là "kẹt" (1–1440 phút) | `15` |

**Ba cách bật/tắt:**

1. **Web UI (khuyến nghị)** — ⚙️ Cài đặt → mục **🧰 Bảo Trì Hàng Đợi Task**: 2 toggle + ô ngưỡng + nút **♻️ Hồi phục ngay**. Có hiệu lực trong ~30 giây (cache cờ).
2. **API trực tiếp**
   ```bash
   GET  /api/settings/task-flags            # xem cờ hiện hành
   PUT  /api/settings/task-flags            # {"queryMode":"legacy","recoveryEnabled":false,"staleMinutes":30}
   POST /api/tasks/maintenance/recover?force=true   # hồi phục ngay (bỏ qua công tắc)
   ```
3. **Biến môi trường Worker** — `wrangler.toml` `[vars]`: `TASKS_QUERY_MODE`, `TASKS_RECOVERY_ENABLED`, `TASKS_STALE_MINUTES`. Cờ trong Firestore **ưu tiên cao hơn** env, nên env chỉ dùng làm mặc định/ép cứng khi Firestore trống.

**Cron mới (cần deploy lại Worker):** `wrangler.toml` thêm `*/15 * * * *` → mỗi 15 phút Worker tự chạy G2 (tự bỏ qua nếu công tắc tắt). Lệnh deploy:
```powershell
cd cloudflare\workers
npx wrangler deploy
```
> Cả PC (Local Agent) lẫn GitHub Actions đều hưởng lợi từ 2 fix này, vì chúng nằm ở tầng Worker API.

**Kiểm chứng nhanh:** bấm **♻️ Hồi phục ngay** → toast báo `Đã kiểm tra N task kẹt, hồi phục M`. Trong log Worker (`wrangler tail`) sẽ thấy dòng `[TaskRecovery] checked=… recovered=…`.

