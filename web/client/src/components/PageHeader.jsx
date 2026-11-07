export default function PageHeader({ eyebrow, title, description, actions, titleId }) {
  return <header className="page-header">
    <div>
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <h1 id={titleId} tabIndex="-1" data-route-heading>{title}</h1>
      {description && <p>{description}</p>}
    </div>
    {actions && <div className="header-actions">{actions}</div>}
  </header>;
}
