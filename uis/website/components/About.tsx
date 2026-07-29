export default function About() {
  return (
    <section
      id="about"
      className="py-20 px-6 bg-white"
      aria-labelledby="about-heading"
    >
      <div className="mx-auto max-w-6xl grid gap-12 lg:grid-cols-2 lg:items-center">
        {/* Text */}
        <div>
          <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-red-600">
            Our story
          </p>
          <h2
            id="about-heading"
            className="mb-6 text-3xl font-bold text-stone-900"
          >
            Founded in Medellín.
            <br />
            Built to last.
          </h2>
          <div className="space-y-4 text-stone-600 leading-relaxed">
            <p>
              Brasaland opened its first location in Medellín in 2008 as a
              family-run grill restaurant. Over fifteen years, the same
              commitment to coal-fired quality grew it into a chain of 14
              company-owned locations — without losing the warmth that made the
              first one work.
            </p>
            <p>
              In 2019, CEO Mariana Restrepo brought Brasaland to the United
              States, opening in Florida. Today, with around 115 employees
              across two countries and USD 6M in annual revenue, the company is
              focused on building the internal systems that let it keep growing
              without losing what makes it good.
            </p>
            <p>
              That effort — <strong>Brasaland Digital</strong> — is how we are
              modernising operations, connecting our locations, and building the
              tools our teams need to serve our guests even better.
            </p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-6">
          {[
            { value: "2008", label: "Founded in Medellín" },
            { value: "14", label: "Company-owned locations" },
            { value: "115", label: "Team members" },
            { value: "2", label: "Countries: Colombia & USA" },
          ].map((stat) => (
            <div
              key={stat.label}
              className="rounded-xl bg-stone-900 p-6 text-white text-center"
            >
              <p className="text-4xl font-bold text-red-400">{stat.value}</p>
              <p className="mt-2 text-sm text-stone-400">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
