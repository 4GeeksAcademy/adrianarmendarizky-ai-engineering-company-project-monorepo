import Link from "next/link";

export default function Hero() {
  return (
    <section
      className="relative bg-stone-900 text-white py-24 px-6 overflow-hidden"
      aria-labelledby="hero-heading"
    >
      {/* Warm ember glow background effect */}
      <div
        className="absolute inset-0 opacity-20"
        style={{
          background:
            "radial-gradient(ellipse at 50% 80%, #E63B2E 0%, #FF8C42 30%, transparent 70%)",
        }}
        aria-hidden="true"
      />

      <div className="relative mx-auto max-w-4xl text-center">
        <p className="mb-4 text-sm font-semibold uppercase tracking-widest text-red-400">
          Al Carbón · Desde 2008
        </p>
        <h1
          id="hero-heading"
          className="mb-6 text-5xl font-bold leading-tight sm:text-6xl"
        >
          The same fire.{" "}
          <span className="text-red-500">Every table.</span>
        </h1>
        <p className="mx-auto mb-10 max-w-2xl text-lg text-stone-300 leading-relaxed">
          Brasaland is a grilled food restaurant chain born in Medellín in 2008.
          14 locations across Colombia and Florida — and one standard that never
          changes: food that tastes the same whether you order it in Medellín or
          Miami.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link
            href="/apply"
            className="rounded-md bg-red-600 px-8 py-3 text-base font-semibold text-white hover:bg-red-700 transition-colors"
          >
            Explore a partnership
          </Link>
          <a
            href="#about"
            className="rounded-md border border-stone-500 px-8 py-3 text-base font-semibold text-stone-300 hover:border-stone-300 hover:text-white transition-colors"
          >
            Our story
          </a>
        </div>
      </div>
    </section>
  );
}
