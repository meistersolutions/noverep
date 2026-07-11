package com.noverep.app;

import androidx.annotation.Nullable;

import java.util.ArrayList;
import java.util.List;

/**
 * Upcoming tracks for background skip / auto-next without relying on a suspended WebView.
 */
public final class PlaybackQueueStore {
    public static final class Item {
        public final String videoId;
        public final String title;
        public final String artist;
        public final String queueItemId;

        public Item(String videoId, String title, String artist, String queueItemId) {
            this.videoId = videoId;
            this.title = title != null ? title : "NoRepeat";
            this.artist = artist != null ? artist : "Playing";
            this.queueItemId = queueItemId != null ? queueItemId : "";
        }
    }

    private static final Object LOCK = new Object();
    private static final List<Item> items = new ArrayList<>();
    private static int index = -1;

    private PlaybackQueueStore() {}

    public static void setQueue(List<Item> newItems, @Nullable String currentVideoId) {
        synchronized (LOCK) {
            // Keep prior index when the same video is still present — avoids races where
            // JS syncs with a stale currentVideoId while ExoPlayer already advanced.
            String previousVideoId = (index >= 0 && index < items.size())
                ? items.get(index).videoId
                : null;

            items.clear();
            if (newItems != null) {
                items.addAll(newItems);
            }
            index = -1;
            if (currentVideoId != null && !currentVideoId.isEmpty()) {
                for (int i = 0; i < items.size(); i++) {
                    if (currentVideoId.equals(items.get(i).videoId)) {
                        index = i;
                        break;
                    }
                }
            }
            // If caller pointed at a video that isn't in the new list, keep playing position
            // when the previously active video is still in the queue.
            if (index < 0 && previousVideoId != null) {
                for (int i = 0; i < items.size(); i++) {
                    if (previousVideoId.equals(items.get(i).videoId)) {
                        index = i;
                        break;
                    }
                }
            }
            if (index < 0 && !items.isEmpty()) {
                index = 0;
            }
        }
    }

    /** Pin the native queue cursor to a video without replacing the list. */
    public static void markCurrent(@Nullable String videoId) {
        if (videoId == null || videoId.isEmpty()) return;
        synchronized (LOCK) {
            for (int i = 0; i < items.size(); i++) {
                if (videoId.equals(items.get(i).videoId)) {
                    index = i;
                    return;
                }
            }
        }
    }

    @Nullable
    public static Item current() {
        synchronized (LOCK) {
            if (index < 0 || index >= items.size()) return null;
            return items.get(index);
        }
    }

    @Nullable
    public static Item advanceNext() {
        synchronized (LOCK) {
            if (items.isEmpty()) return null;
            if (index + 1 >= items.size()) return null;
            index += 1;
            return items.get(index);
        }
    }

    @Nullable
    public static Item advancePrevious() {
        synchronized (LOCK) {
            if (items.isEmpty()) return null;
            if (index <= 0) return null;
            index -= 1;
            return items.get(index);
        }
    }

    public static int size() {
        synchronized (LOCK) {
            return items.size();
        }
    }
}
