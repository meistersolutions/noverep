import { create } from 'zustand';
import { api } from '@/lib/api';

interface HomeSection {
  title: string;
  tracks: import('@/lib/api').Track[];
}

interface HomeState {
  sections: HomeSection[];
  loaded: boolean;
  loading: boolean;
  load: (force?: boolean) => Promise<void>;
}

export const useHomeStore = create<HomeState>((set, get) => ({
  sections: [],
  loaded: false,
  loading: false,

  load: async (force = false) => {
    if (get().loading) return;
    if (get().loaded && !force) return;
    set({ loading: true });
    try {
      const res = await api.getHomeRecommendations();
      set({ sections: res.sections, loaded: true });
    } finally {
      set({ loading: false });
    }
  },
}));
