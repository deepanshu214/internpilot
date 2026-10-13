// One-page resume. All content arrives as JSON via sys.inputs.data, so text is never parsed as markup.
#let d = json(bytes(sys.inputs.data))
#let accent = rgb("#1f3a5f")

#set document(title: d.name + " — Resume", author: d.name)
#set page(paper: "a4", margin: (x: 1.35cm, top: 1.1cm, bottom: 1.0cm))
#set text(font: ("New Computer Modern", "Libertinus Serif"), size: 10pt, lang: "en")
#set par(justify: false, leading: 0.48em, spacing: 0.45em)
#set block(spacing: 0.45em)
#set list(indent: 0.6em, body-indent: 0.45em, spacing: 0.32em)

#let section(title) = {
  v(0.35em)
  block(width: 100%, stroke: (bottom: 0.6pt + accent), inset: (bottom: 2.5pt),
    text(size: 10.5pt, weight: "bold", fill: accent, tracking: 0.04em, upper(title)))
}

#let entry(lhs, rhs) = grid(columns: (1fr, auto), lhs, align(right, rhs))

#align(center, block(below: 0.6em, text(size: 20pt, weight: "bold", d.name)))
#align(center, text(size: 9.5pt, d.contacts.map(c => if c.url != "" { link(c.url, c.label) } else { c.label }).join("  |  ")))

#section("Summary")
#text(d.summary)

#section("Education")
#for e in d.education [
  #grid(columns: (1fr, auto), row-gutter: 0.35em, strong(e.school), align(right, e.dates), text(e.detail), [])
]

#if d.experience.len() > 0 [
  #section("Experience")
  #for x in d.experience [
    #entry([#strong(x.name) — #emph(x.role)], emph(x.dates))
    #list(..x.bullets.map(b => text(b)))
  ]
]

#section("Projects")
#for p in d.projects [
  #entry(
    [#strong(p.name) #h(0.3em) #text(size: 9pt, emph(p.stack.join(", ")))],
    if p.url != "" { link(p.url, text(size: 9pt, fill: accent, "GitHub")) } else { [] },
  )
  #list(..p.bullets.map(b => text(b)))
]

#section("Technical Skills")
#for (group, items) in d.skills [
  #strong(group): #items.join(", ") \
]

#if d.certifications.len() > 0 [
  #section("Certifications")
  #for c in d.certifications [- #c]
]

#if d.achievements.len() > 0 [
  #section("Achievements")
  #for a in d.achievements [- #a]
]
