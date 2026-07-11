import type { SVGProps } from "react";

type Props = SVGProps<SVGSVGElement>;

const Icon = ({ children, ...props }: Props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    {children}
  </svg>
);

export const ArrowUpIcon = (props: Props) => <Icon {...props}><path d="m18 15-6-6-6 6" /></Icon>;
export const CheckIcon = (props: Props) => <Icon {...props}><path d="m5 12 4 4L19 6" /></Icon>;
export const ChevronIcon = (props: Props) => <Icon {...props}><path d="m9 18 6-6-6-6" /></Icon>;
export const ClockIcon = (props: Props) => <Icon {...props}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Icon>;
export const LockIcon = (props: Props) => <Icon {...props}><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></Icon>;
export const MenuIcon = (props: Props) => <Icon {...props}><path d="M4 7h16M4 12h16M4 17h16" /></Icon>;
export const MicrophoneIcon = (props: Props) => <Icon {...props}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" /></Icon>;
export const MonitorIcon = (props: Props) => <Icon {...props}><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></Icon>;
export const PackageIcon = (props: Props) => <Icon {...props}><path d="m4 7 8-4 8 4-8 4-8-4Z" /><path d="m4 7 8 4 8-4v10l-8 4-8-4V7Z" /><path d="M12 11v10" /></Icon>;
export const PlusIcon = (props: Props) => <Icon {...props}><path d="M12 5v14M5 12h14" /></Icon>;
export const RefreshIcon = (props: Props) => <Icon {...props}><path d="M20 7h-5V2" /><path d="M20 7a8 8 0 1 0 1 7" /></Icon>;
export const ShieldIcon = (props: Props) => <Icon {...props}><path d="M12 3 5 6v5c0 4.5 2.8 8.1 7 10 4.2-1.9 7-5.5 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></Icon>;
export const SparkIcon = (props: Props) => <Icon {...props}><path d="m12 3 1.2 4.1L17 9l-3.8 1.9L12 15l-1.2-4.1L7 9l3.8-1.9L12 3Z" /><path d="m19 15 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7L19 15Z" /></Icon>;
export const StopIcon = (props: Props) => <Icon {...props}><rect x="7" y="7" width="10" height="10" rx="1" /></Icon>;
export const TruckIcon = (props: Props) => <Icon {...props}><path d="M3 6h11v11H3zM14 10h4l3 3v4h-7z" /><circle cx="7" cy="18" r="2" /><circle cx="18" cy="18" r="2" /></Icon>;
export const XIcon = (props: Props) => <Icon {...props}><path d="m6 6 12 12M18 6 6 18" /></Icon>;
