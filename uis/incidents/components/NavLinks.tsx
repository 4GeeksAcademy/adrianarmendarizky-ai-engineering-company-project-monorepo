"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Analyze CSV" },
  { href: "/register", label: "Register Incident" },
  { href: "/list", label: "Incidents" },
  { href: "/summary", label: "Summary" },
];

export default function NavLinks() {
  const pathname = usePathname();

  return (
    <nav className="ml-6 flex gap-4 text-sm">
      {LINKS.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={
              active
                ? "text-white font-medium border-b-2 border-red-500 pb-0.5"
                : "text-stone-300 hover:text-white pb-0.5"
            }
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
