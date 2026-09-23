// src/lib/citations.js — Citation Engine: APA 7 / IEEE / Harvard (§3.3) (<230 lines)
// Quy ước tên: NGƯỜI VIỆT (họ đứng trước) — token đầu là họ, các token sau là tên gọi.
// Ví dụ: "Nguyen Van A" → APA: "Nguyen, V. A." · IEEE: "V. A. Nguyen".

const REFERENCE_HEADING = '## 📚 Danh mục Tham khảo';
const MAX_AUTHORS_INLINE = 2;

const txt = (v) => (v === null || v === undefined ? '' : String(v).trim());

/** Chuẩn hoá 1 nguồn về object phẳng dùng cho formatter */
export function normalizeSource(input = {}) {
  const src = typeof input === 'string' ? { title: input } : (input || {});
  return {
    source_id: txt(src.source_id || src.file_id),
    title: txt(src.title || src.source_name),
    filename: txt(src.filename),
    authors: src.authors,
    year: txt(src.year),
    publisher: txt(src.publisher),
    journal: txt(src.journal),
    url: txt(src.url),
    doi: txt(src.doi),
    page: txt(src.page),
    accessed: txt(src.accessed),
  };
}

/** Parse authors: JSON array string | mảng | chuỗi "A; B" hoặc "A & B" */
export function parseAuthors(authors) {
  if (Array.isArray(authors)) return authors.map(txt).filter(Boolean);
  const raw = txt(authors);
  if (!raw) return [];
  if (raw.startsWith('[')) {
    try {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) return arr.map(txt).filter(Boolean);
    } catch (err) {
      // không phải JSON → coi như chuỗi phân tách
    }
  }
  return raw.split(/[;]|\s+&\s+/).map((a) => a.trim()).filter(Boolean);
}

const firstInitial = (word) => (txt(word) ? `${txt(word)[0].toUpperCase()}.` : '');

/** Tách tên → {surname, initials} theo quy ước họ đứng trước */
function splitName(name) {
  const raw = txt(name);
  if (!raw) return null;
  if (raw.includes(',')) {
    const [surname, rest] = raw.split(',');
    const initials = txt(rest).split(/\s+/).filter(Boolean).map(firstInitial).join(' ');
    return { surname: txt(surname), initials };
  }
  const tokens = raw.split(/\s+/).filter(Boolean);
  return {
    surname: tokens[0],
    initials: tokens.slice(1).map(firstInitial).join(' '),
  };
}

const parsedAuthors = (authors) => parseAuthors(authors).map(splitName).filter(Boolean);


/** APA 7: "Nguyen, V. A., & Tran, T. B." */
export function formatAuthorsApa(authors) {
  const list = parsedAuthors(authors)
    .map((a) => (a.initials ? `${a.surname}, ${a.initials}` : a.surname));
  if (list.length === 0) return '';
  if (list.length === 1) return list[0];
  return `${list.slice(0, -1).join(', ')}, & ${list[list.length - 1]}`;
}

/** IEEE: "V. A. Nguyen and T. B. Tran" */
export function formatAuthorsIeee(authors) {
  const list = parsedAuthors(authors)
    .map((a) => (a.initials ? `${a.initials} ${a.surname}` : a.surname));
  if (list.length === 0) return '';
  if (list.length === 1) return list[0];
  if (list.length === 2) return `${list[0]} and ${list[1]}`;
  return `${list.slice(0, -1).join(', ')}, and ${list[list.length - 1]}`;
}

/** Harvard: cùng quy ước APA (họ, viết tắt) */
export function formatAuthorsHarvard(authors) {
  return formatAuthorsApa(authors);
}

const cleanDoi = (doi) => txt(doi).replace(/^https?:\/\/(dx\.)?doi\.org\//i, '');
const sourceTitle = (s) => s.title || s.filename || 'Không rõ tiêu đề';

/** APA 7 — Author, A. A. (Year). Title. Journal. Publisher. https://doi.org/... */
export function formatApa7(src) {
  const authors = formatAuthorsApa(src.authors);
  const year = src.year || 'n.d.';
  const parts = [`${authors ? `${authors} ` : ''}(${year}).`, `${sourceTitle(src)}.`];
  if (src.journal) parts.push(`${src.journal}.`);
  if (src.publisher) parts.push(`${src.publisher}.`);
  if (src.doi) parts.push(`https://doi.org/${cleanDoi(src.doi)}`);
  else if (src.url) parts.push(src.url);
  return parts.join(' ').replace(/\s+/g, ' ').trim();
}

/** IEEE — [n] A. Author, "Title," Journal, pp. xx, year, doi: xx. */
export function formatIeee(src, index = 1) {
  const authors = formatAuthorsIeee(src.authors);
  const parts = [`[${index}]`];
  if (authors) parts.push(authors);
  parts.push(`"${sourceTitle(src)}"`);
  if (src.journal) parts.push(src.journal);
  else if (src.publisher) parts.push(src.publisher);
  if (src.page) parts.push(`pp. ${src.page}`);
  if (src.year) parts.push(src.year);
  let entry = parts.join(', ');
  if (src.doi) entry += `, doi: ${cleanDoi(src.doi)}.`;
  else if (src.url) entry += `, [Online]. Available: ${src.url}`;
  else entry += '.';
  return entry;
}

/** Harvard — Author (Year) 'Title', Publisher. Available at: URL */
export function formatHarvard(src) {
  const authors = formatAuthorsHarvard(src.authors);
  const year = src.year || 'n.d.';
  const parts = [authors ? `${authors} (${year})` : `(${year})`, `'${sourceTitle(src)}'`];
  if (src.journal) parts.push(src.journal);
  if (src.publisher) parts.push(src.publisher);
  let entry = parts.join(', ');
  if (src.doi) entry += `. Available at: https://doi.org/${cleanDoi(src.doi)}`;
  else if (src.url) entry += `. Available at: ${src.url}`;
  if (src.accessed) entry += ` (Accessed: ${src.accessed})`;
  return `${entry}.`;
}

/** §3.3 — doi+journal → ieee; publisher+year (không journal) → apa7; chỉ url → harvard */
export function detectCitationStyle(meta = {}) {
  const m = meta || {};
  if (txt(m.doi) && txt(m.journal)) return 'ieee';
  if (txt(m.publisher) && txt(m.year) && !txt(m.journal)) return 'apa7';
  if (txt(m.url)) return 'harvard';
  if (txt(m.journal)) return 'ieee';
  return 'apa7'; // mặc định học thuật
}

/** Bầu chọn style từ danh sách nguồn (nhiều phiếu nhất) */
export function detectStyleFromSources(sources = []) {
  const votes = { apa7: 0, ieee: 0, harvard: 0 };
  for (const src of sources) votes[detectCitationStyle(src)] += 1;
  return Object.entries(votes).sort((a, b) => b[1] - a[1])[0][0];
}

const inlineAuthor = (authors) => {
  const list = parsedAuthors(authors);
  if (list.length === 0) return '';
  if (list.length <= MAX_AUTHORS_INLINE) return list.map((a) => a.surname).join(' & ');
  return `${list[0].surname} et al.`;
};

/** Marker trong thân bài: IEEE → [n]; APA/Harvard → (Nguyen & Tran, 2024) */
export function inlineMarker(src, style, index = 1) {
  if (style === 'ieee') return `[${index}]`;
  const who = inlineAuthor(src.authors) || 'Nguồn';
  return `(${who}, ${src.year || 'n.d.'})`;
}

/** §3.3 — markdown "## 📚 Danh mục Tham khảo" + danh sách số thứ tự */
export function buildReferenceBlock(references = []) {
  const list = (references || []).filter((r) => txt(r));
  if (list.length === 0) return '';
  const body = list.map((ref, i) => `${i + 1}. ${ref}`).join('\n');
  return `${REFERENCE_HEADING}\n\n${body}`;
}

/**
 * §3.3 — Chuẩn hoá + định dạng danh mục tham khảo.
 * @param {Array|string} sources mảng nguồn (hoặc JSON string)
 * @param {string} style 'auto'|'apa7'|'ieee'|'harvard'
 * @returns {{style: string, references: string[], reference_block: string, inline_markers: string[]}}
 */
export function formatReferences(sources = [], style = 'auto') {
  let input = sources;
  if (typeof input === 'string') {
    try { input = JSON.parse(input); } catch (err) { input = []; }
  }
  const list = (Array.isArray(input) ? input : []).map(normalizeSource);
  const allowed = ['apa7', 'ieee', 'harvard'];
  const resolved = allowed.includes(style) ? style : detectStyleFromSources(list);

  const references = list.map((src, i) => {
    if (resolved === 'ieee') return formatIeee(src, i + 1);
    if (resolved === 'harvard') return formatHarvard(src);
    return formatApa7(src);
  });

  return {
    style: resolved,
    references,
    reference_block: buildReferenceBlock(references),
    inline_markers: list.map((src, i) => inlineMarker(src, resolved, i + 1)),
  };
}

/** Map file doc Firestore → nguồn cho formatter (chat/agent trả citations) */
export function sourceFromFileDoc(file = {}, extra = {}) {
  return normalizeSource({
    source_id: extra.source_id || file._id || file.id || '',
    title: extra.title || file.title || file.filename || '',
    filename: file.filename || '',
    authors: extra.authors || file.authors || '',
    year: extra.year || file.year || '',
    publisher: extra.publisher || file.publisher || '',
    journal: extra.journal || file.journal || '',
    url: extra.url || file.url || file.web_url || '',
    doi: extra.doi || file.doi || '',
    page: extra.page || file.page || '',
  });
}
