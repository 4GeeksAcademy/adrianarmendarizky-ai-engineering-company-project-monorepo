import Link from "next/link";

export default function Header() {
  return (
    <header className="sticky top-0 z-50 bg-stone-900 text-white shadow-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          {/* Coal-B mark — inline SVG matching the brand identity */}
          <svg
            viewBox="0 0 48 48"
            width="36"
            height="36"
            aria-hidden="true"
            xmlns="http://www.w3.org/2000/svg"
          >
            <defs>
              <radialGradient id="hglow" cx="50%" cy="55%" r="60%">
                <stop offset="0%" stopColor="#FFE08A" />
                <stop offset="40%" stopColor="#FF8C42" />
                <stop offset="100%" stopColor="#E63B2E" stopOpacity="0" />
              </radialGradient>
            </defs>
            <ellipse cx="24" cy="44" rx="18" ry="3" fill="#E63B2E" opacity="0.3" />
            <ellipse cx="24" cy="24" rx="18" ry="20" fill="url(#hglow)" />
            <polygon points="10,8 18,7 19,18 11,19" fill="#3A322C" />
            <polygon points="11,20 19,19 18,30 10,31" fill="#3A322C" />
            <polygon points="10,32 19,31 19,41 11,41" fill="#3A322C" />
            <polygon points="21,7 30,8 31,12 20,12" fill="#3A322C" />
            <polygon points="32,9 37,13 36,20 31,21 30,14" fill="#3A322C" />
            <polygon points="21,20 31,19 32,24 21,25" fill="#3A322C" />
            <polygon points="33,22 39,27 38,36 33,39 31,30" fill="#3A322C" />
            <polygon points="21,37 30,37 31,41 21,41" fill="#3A322C" />
          </svg>
          <span className="text-xl font-bold tracking-wide">
            <span className="text-red-500">BRASA</span>LAND
          </span>
        </div>

        <nav aria-label="Main navigation">
          <ul className="flex items-center gap-6 text-sm font-medium">
            <li>
              <a href="#about" className="hover:text-red-400 transition-colors">
                About
              </a>
            </li>
            <li>
              <a href="#features" className="hover:text-red-400 transition-colors">
                Experience
              </a>
            </li>
            <li>
              <Link
                href="/apply"
                className="rounded-md bg-red-600 px-4 py-2 text-white hover:bg-red-700 transition-colors"
              >
                Apply now
              </Link>
            </li>
          </ul>
        </nav>
      </div>
    </header>
  );
}
