type BrandMarkProps = { size?: number };

export default function BrandMark({ size = 34 }: BrandMarkProps) {
  return (
    <span className="brand-symbol" style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 76 76" fill="none">
        <path d="M28 22h-5a3 3 0 0 0-3 3v5M48 22h5a3 3 0 0 1 3 3v5M20 46v5a3 3 0 0 0 3 3h5M56 46v5a3 3 0 0 1-3 3h-5" stroke="currentColor" strokeWidth="4.5" strokeLinecap="round" />
        <circle cx="31" cy="35" r="2" fill="currentColor" />
        <circle cx="45" cy="35" r="2" fill="currentColor" />
        <path d="M29 43c2.4 2.8 5.4 4.2 9 4.2s6.6-1.4 9-4.2" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" />
      </svg>
    </span>
  );
}
