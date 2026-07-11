import { create } from 'zustand';
import { api } from '@/lib/api';
import {
  readCachedHome,
  writeCachedHome,
  type HomeSection,
} from '@/lib/sessionMemoryCache';

interface HomeState {
  sections: HomeSection[];
  loaded: boolean;
  loading: boolean;
  refreshing: boolean;
  load: (force?: boolean) => Promise<void>;
}

const cachedHome = readCachedHome();

export const useHomeStore = create<HomeState>((set, get) => ({
  sections: cachedHome?.sections ?? [],
  loaded: Boolean(cachedHome?.sections?.length),
  loading: false,
  refreshing: false,

  load: async (force = false) => {
    const hasContent = get().sections.length > 0;

    // Soft navigation: show cached/current content, refresh in background.
    if (!force && hasContent) {
      if (get().refreshing || get().loading) return;
      set({ refreshing: true });
      try {
        const res = await api.getHomeRecommendations();
        set({ sections: res.sections, loaded: true });
        writeCachedHome(res.sections);
      } catch {
        /* keep existing sections */
      } finally {
        set({ refreshing: false });
      }
      return;
    }

    if (get().loading) return;

    // First paint with no cache, or explicit Refresh: show loading state.
    set({ loading: true, refreshing: force });
    try {
      const res = await api.getHomeRecommendations();
      set({ sections: res.sections, loaded: true });
      writeCachedHome(res.sections);
    } catch {
      if (!hasContent) set({ sections: [], loaded: true });
    } finally {
      set({ loading: false, refreshing: false });
    }
  },
}));
