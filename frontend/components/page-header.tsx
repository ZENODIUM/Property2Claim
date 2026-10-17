export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description: string; actions?: React.ReactNode }) {
  return <div className="mb-8 flex flex-wrap items-end justify-between gap-5"><div>{eyebrow && <div className="eyebrow mb-3">{eyebrow}</div>}<h1 className="text-3xl font-medium tracking-[-.035em] text-slate-100 sm:text-[2.65rem] sm:leading-[1.05]">{title}</h1><p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">{description}</p></div>{actions && <div className="flex flex-wrap gap-2">{actions}</div>}</div>;
}
