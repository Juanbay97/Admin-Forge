// Deliberately generic: it must not reveal whether an organisation exists.
export function NotFound() {
  return (
    <section className="flex flex-col gap-2">
      <h1 className="font-title text-page font-bold text-fg">Not found</h1>
      <p className="text-body text-muted">The page you requested could not be found.</p>
    </section>
  );
}