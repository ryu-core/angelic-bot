import PageHeader from "./PageHeader.jsx";

export default function PublicLegalPage({ title, description, sections }) {
  return <div className="page-shell route-stage route-reveal legal-shell">
    <PageHeader eyebrow="Legal" title={title} description={description} />
    <div className="legal-layout">
      <aside className="legal-index" aria-label={`${title} sections`}>
        <span>Document index</span>
        <nav>{sections.map((section, index) => <a href={`#${section.id}`} key={section.id}><span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>{section.title}</a>)}</nav>
      </aside>
      <article className="prose-panel legal-card" aria-label={title}>
        {sections.map((section) => <section id={section.id} key={section.id}>
          <h2>{section.title}</h2>
          <p>{section.body}</p>
        </section>)}
      </article>
    </div>
  </div>;
}
