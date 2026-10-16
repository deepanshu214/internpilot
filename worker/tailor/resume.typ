// One-page resume in the style of Jake's template (the user's own resume format).
// All content arrives as JSON via sys.inputs.data, so text is never parsed as markup.
#let d = json(bytes(sys.inputs.data))

#set document(title: d.name + " — Resume", author: d.name)
#set page(paper: "a4", margin: (x: 1.15cm, top: 0.95cm, bottom: 0.9cm))
#set text(font: ("New Computer Modern", "Libertinus Serif"), size: 10.5pt, lang: "en")
#set par(justify: false, leading: 0.5em, spacing: 0.5em)
#set block(spacing: 0.5em)
#set list(indent: 0.9em, body-indent: 0.45em, spacing: 0.34em)

#let section(title) = {
  v(0.4em)
  block(width: 100%, stroke: (bottom: 0.6pt), inset: (bottom: 2.5pt), text(size: 12pt, smallcaps(title)))
  v(0.1em)
}

// Two-column row: left content, right-aligned content (dates / locations).
#let row(lhs, rhs) = grid(columns: (1fr, auto), column-gutter: 0.6em, lhs, align(right, rhs))
#let maybe-link(url, label) = if url != "" { link(url, underline(label)) } else { label }

#align(center, block(below: 0.45em, text(size: 24pt, smallcaps(d.name))))
#for line in d.contact_lines [
  #align(center, text(size: 9.8pt, line.map(c => maybe-link(c.url, c.label)).join("  |  ")))
]

#section("Education")
#for e in d.education [
  #row(strong(e.school), e.location)
  #v(-0.05em)
  #row(emph(e.detail), emph(e.dates))
  #if e.coursework != "" [
    #list([#strong("Coursework:") #e.coursework])
  ]
]

#if d.experience.len() > 0 [
  #section("Experience")
  #for x in d.experience [
    #row(strong(x.role), x.dates)
    #v(-0.05em)
    #row(emph(x.org), emph(x.location))
    #list(..x.bullets.map(b => text(b)))
  ]
]

#section("Projects")
#for p in d.projects [
  #row(
    [#strong(p.name) | #emph(p.stack.join(", "))#if p.url != "" [ | #link(p.url, underline("GitHub"))] else if p.note != "" [ | #emph(p.note)]],
    p.dates,
  )
  #list(..p.bullets.map(b => text(b)))
]

#section("Technical Skills")
#for (group, items) in d.skills [
  #strong(group): #items.join(", ") \
]

#if d.certifications.len() + d.achievements.len() > 0 [
  #section("Certifications & Achievements")
  #for c in d.certifications [
    #let parts = c.text.split(" (")
    #row([#strong(parts.at(0))#if parts.len() > 1 [ #("(" + parts.slice(1).join(" ("))]#if c.url != "" [ | #link(c.url, underline("Credential"))]], c.dates)
  ]
  #if d.achievements.len() > 0 [
    #d.achievements.join("  |  ")
  ]
]
