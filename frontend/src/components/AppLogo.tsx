interface AppLogoProps {
  className?: string;
  alt?: string;
}

export function AppLogo({ className = 'size-6', alt = 'ReadingDNA' }: AppLogoProps) {
  return <img src="/favicon.svg" alt={alt} className={className} />;
}
