// Minimal inline OS logos so the download UI ships without binary image assets.
export default function OSIcon({ name, className = "h-7 w-7" }) {
  if (name === "windows")
    return (
      <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
        <path d="M3 5.1L10.4 4v7.3H3V5.1zm0 13.8L10.4 20v-7.2H3v6.1zM11.3 3.9L21 2.5v8.8h-9.7V3.9zm0 16.2L21 21.5v-8.7h-9.7v7.3z" />
      </svg>
    );
  if (name === "apple")
    return (
      <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
        <path d="M16.4 12.7c0-2 1.6-3 1.7-3-1-1.4-2.4-1.6-2.9-1.6-1.2-.1-2.4.7-3 .7-.6 0-1.6-.7-2.6-.7-1.3 0-2.6.8-3.3 2-1.4 2.4-.4 6 1 8 .7 1 1.4 2.1 2.4 2 1-.1 1.3-.6 2.5-.6s1.5.6 2.5.6 1.7-1 2.3-2c.7-1.1 1-2.2 1-2.3 0 0-2-.8-2-3.1zM14.6 6c.5-.7.9-1.6.8-2.6-.8 0-1.8.5-2.4 1.2-.5.6-1 1.6-.8 2.5.9.1 1.8-.4 2.4-1.1z" />
      </svg>
    );
  // linux
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M12.3 2c-1.6 0-2.9 1.6-2.7 3.6.1 1 .1 2.3-.3 3.2-.5 1-1.6 2-2.2 3.4-.6 1.4-.7 2.9.1 3.8.3.4.2.9 0 1.5-.3.7-.7 1.4-.4 2 .3.6 1.1.6 1.8.4.7-.2 1.4-.4 2.2-.1.9.3 1.6.6 2.4.4.7-.2 1.1-.8 1.1-1.5 0-.5.2-.8.6-1.2.8-.8 1.3-1.9 1-3.1-.3-1.2-1.2-2.2-1.8-3.3-.4-.8-.5-2-.4-3 .2-2-.9-3.6-2.4-3.6zm-1 4.1c.4 0 .7.4.7.9s-.3.9-.7.9-.7-.4-.7-.9.3-.9.7-.9zm2.5 0c.4 0 .7.4.7.9s-.3.9-.7.9-.7-.4-.7-.9.3-.9.7-.9z" />
    </svg>
  );
}
