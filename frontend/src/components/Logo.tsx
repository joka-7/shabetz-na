/** The Shabetz mark: two overlapping shift blocks and a status dot. */
export function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" fill="none" className={className} aria-hidden>
      <rect width="40" height="40" rx="10" fill="#4F46E5" />
      <path
        d="M11 14a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2h-6a2 2 0 0 1-2-2z"
        fill="white"
        fillOpacity="0.95"
      />
      <path d="M21 20a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2z" fill="#A5B4FC" />
      <circle cx="15.5" cy="27.5" r="2.5" fill="#38BDF8" />
      <path d="M24 13h3" stroke="white" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
