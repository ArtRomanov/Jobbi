// The ONE stylesheet of the designed CV (backlog #11). The editor preview and
// the downloaded HTML both use it, scoped under `.cv-doc`, so they look the
// same. Our own constant CSS: never put CV text in here.

/** Colours from the reference design (research_11 §1.2). */
export const CV_LAYOUT_COLORS = {
  ink: "#1C1F23",
  body: "#3A4046",
  muted: "#6B737B",
  accent: "#1F6FD6",
  rule: "#2B2F34",
} as const;

const HEADING_FONT = `"Roboto Condensed", "Arial Narrow", Arial, sans-serif`;
const BODY_FONT = `"Roboto Mono", ui-monospace, Menlo, Consolas, monospace`;
const { ink, body, muted, accent, rule } = CV_LAYOUT_COLORS;

/** Class names the view renders (kept in one place with the CSS that styles them). */
export const CV_LAYOUT_CLASSES = {
  root: "cv-doc",
  header: "cv-header",
  name: "cv-name",
  title: "cv-title",
  rule: "cv-rule",
  contacts: "cv-contacts",
  separator: "cv-sep",
  section: "cv-section",
  sectionHeading: "cv-section-heading",
  entry: "cv-entry",
  entryLead: "cv-entry-lead",
  entryHead: "cv-entry-head",
  entryTitle: "cv-entry-title",
  entryDates: "cv-entry-dates",
  paragraph: "cv-p",
  context: "cv-context",
  list: "cv-list",
  orderedList: "cv-list-ordered",
  raw: "cv-raw",
  subheading: "cv-subheading",
} as const;

export const CV_LAYOUT_CSS = `
.cv-doc{font-family:${BODY_FONT};font-size:9pt;line-height:1.4;color:${body};overflow-wrap:anywhere;-webkit-print-color-adjust:exact;print-color-adjust:exact;text-align:left}
.cv-doc *{box-sizing:border-box}
.cv-doc :where(h1,h2,h3,h4,h5,p,ul,ol,li){margin:0;padding:0;font-size:inherit}
.cv-doc :where(strong){font-weight:700;color:${ink}}
.cv-doc :where(a){color:${accent};text-decoration:none}
.cv-doc :where(a:hover){text-decoration:underline}
.cv-header{margin:0 0 6pt}
.cv-name,.cv-title{font-family:${HEADING_FONT};font-size:23pt;font-weight:400;line-height:1.1;text-transform:uppercase;color:${ink};letter-spacing:.01em}
.cv-rule{height:0;border-top:3.7pt solid ${rule};margin:7pt 0 10pt}
.cv-contacts{font-family:${HEADING_FONT};font-size:9.6pt;line-height:1.5;color:${ink}}
.cv-sep{color:${muted}}
.cv-section{margin-top:14pt}
.cv-section:first-child{margin-top:0}
.cv-header+.cv-section{margin-top:12pt}
.cv-section-heading{font-family:${HEADING_FONT};font-size:12pt;font-weight:500;line-height:1.2;text-transform:uppercase;letter-spacing:.02em;color:${ink};margin:0 0 5pt;break-after:avoid;page-break-after:avoid}
.cv-entry{margin-top:7pt}
.cv-entry:first-child{margin-top:0}
.cv-entry-lead{break-inside:avoid;page-break-inside:avoid}
.cv-entry-head{display:flex;justify-content:space-between;align-items:baseline;gap:8pt;margin:0 0 2pt;break-after:avoid;page-break-after:avoid}
.cv-entry-title{flex:1 1 auto;min-width:0;font-family:${BODY_FONT};font-size:9.5pt;font-weight:700;color:${ink}}
.cv-entry-dates{flex:0 0 auto;max-width:45%;font-size:8pt;color:${muted};text-align:right}
.cv-p{margin:0 0 5.5pt;orphans:2;widows:2}
.cv-context{color:${muted}}
.cv-context strong{color:${muted}}
.cv-raw{margin:0 0 5.5pt;white-space:pre-wrap}
.cv-subheading{font-size:9.5pt;font-weight:700;color:${ink};margin:0 0 2pt}
.cv-list{list-style:none;margin:0 0 5.5pt;padding:0}
.cv-list>li{position:relative;padding-left:15pt;margin:0 0 2pt;orphans:2;widows:2}
.cv-list>li::before{content:"";position:absolute;left:2.3pt;top:calc(.7em - 1.5pt);width:0;height:0;border:1.5pt solid ${accent};border-radius:50%}
.cv-list .cv-list{margin:2pt 0 0}
.cv-list .cv-p,.cv-list .cv-raw{margin:0}
.cv-list-ordered{list-style:decimal;padding-left:15pt}
.cv-list-ordered>li{padding-left:2pt}
.cv-list-ordered>li::before{content:none}
`;
