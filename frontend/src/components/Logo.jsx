export default function Logo({ size = 30 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
    >
      <g transform="rotate(-9 24 24)">
        <path
          d="M17 5h17a7 7 0 0 1 7 7v22a7 7 0 0 1-7 7H14a7 7 0 0 1-7-7V15z"
          fill="#e37455"
        />
        <circle cx="16.5" cy="13.5" r="2.7" fill="#1e1543" />
      </g>
      <path
        d="M9 11c3.5-3.6 8-4.2 11.6-2.3"
        stroke="#87ddc2"
        strokeWidth="3.1"
        strokeLinecap="round"
      />
      <circle cx="25.5" cy="27" r="8.9" fill="#fcf6ed" />
      <path
        d="M21.4 27.4l3.1 3.1 5.8-6.6"
        stroke="#3fae8c"
        strokeWidth="3.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M31.9 33.4l7.2 7.2"
        stroke="#1e1543"
        strokeWidth="3.8"
        strokeLinecap="round"
      />
    </svg>
  );
}
