import { Disc3 } from 'lucide-react';
import { DiscoverModeToggle } from '@/components/DiscoverModeToggle';
import { YoutubeDiscoveryToggle } from '@/components/YoutubeDiscoveryToggle';

interface MobileHeaderProps {
  title: string;
  showDiscoverToggle?: boolean;
  showYoutubeDiscoveryToggle?: boolean;
}

export function MobileHeader({
  title,
  showDiscoverToggle = false,
  showYoutubeDiscoveryToggle = false,
}: MobileHeaderProps) {
  return (
    <header className="md:hidden sticky top-0 z-30 glass border-b border-white/10 px-4 py-3 mb-4 -mx-4 -mt-4 safe-top">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Disc3 className="w-5 h-5 text-accent shrink-0" />
          <h1 className="font-bold truncate">{title}</h1>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {showYoutubeDiscoveryToggle && <YoutubeDiscoveryToggle compact />}
          {showDiscoverToggle && <DiscoverModeToggle compact />}
        </div>
      </div>
    </header>
  );
}
