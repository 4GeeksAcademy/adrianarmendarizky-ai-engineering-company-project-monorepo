import Link from "next/link";

export default function Footer() {
  return (
    <footer className="bg-stone-900 text-stone-400 py-12 px-6">
      <div className="mx-auto max-w-6xl grid gap-8 sm:grid-cols-3">
        {/* Brand */}
        <div>
          <p className="mb-3 text-lg font-bold text-white">
            <span className="text-red-500">BRASA</span>LAND
          </p>
          <p className="text-sm leading-relaxed">
            Al Carbón · Desde 2008
            <br />
            Consistent food. Warm service. Fast kitchen.
          </p>
        </div>

        {/* Medellín HQ */}
        <address className="not-italic text-sm">
          <p className="mb-2 font-semibold text-white">
            Headquarters — Medellín
          </p>
          <p>Brasaland S.A.S.</p>
          <p>Medellín, Antioquia, Colombia</p>
          <p className="mt-2">
            <a
              href="mailto:digital@brasaland.co"
              className="hover:text-white transition-colors"
            >
              digital@brasaland.co
            </a>
          </p>
        </address>

        {/* Miami office */}
        <address className="not-italic text-sm">
          <p className="mb-2 font-semibold text-white">
            Commercial office — Miami
          </p>
          <p>Brasaland USA Inc.</p>
          <p>Miami, Florida, USA</p>
          <p className="mt-2">
            <a
              href="mailto:florida@brasaland.co"
              className="hover:text-white transition-colors"
            >
              florida@brasaland.co
            </a>
          </p>
        </address>
      </div>

      <div className="mx-auto mt-10 max-w-6xl flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-stone-800 pt-6 text-xs">
        <p>© {new Date().getFullYear()} Brasaland. All rights reserved.</p>
        <Link
          href="/apply"
          className="text-red-400 hover:text-red-300 transition-colors"
        >
          Partnership enquiries →
        </Link>
      </div>
    </footer>
  );
}
