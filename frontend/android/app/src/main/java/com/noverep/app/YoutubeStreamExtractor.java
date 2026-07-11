package com.noverep.app;

import android.util.Log;

import org.schabi.newpipe.extractor.NewPipe;
import org.schabi.newpipe.extractor.ServiceList;
import org.schabi.newpipe.extractor.stream.AudioStream;
import org.schabi.newpipe.extractor.stream.StreamInfo;
import org.schabi.newpipe.extractor.stream.StreamType;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;

/**
 * Client-side YouTube audio URL extraction via NewPipe Extractor
 * (same approach as NewPipe — runs on the phone, not the Render API).
 */
public final class YoutubeStreamExtractor {
    private static final String TAG = "YoutubeStreamExtractor";
    private static volatile boolean initialized;

    private YoutubeStreamExtractor() {}

    private static void ensureInit() {
        if (initialized) return;
        synchronized (YoutubeStreamExtractor.class) {
            if (initialized) return;
            NewPipe.init(OkHttpDownloader.getInstance());
            initialized = true;
        }
    }

    public static final class Result {
        public final String url;
        public final String title;
        public final String artist;
        public final long durationSeconds;
        public final String mimeType;
        public final String headersJson;

        Result(
            String url,
            String title,
            String artist,
            long durationSeconds,
            String mimeType,
            String headersJson
        ) {
            this.url = url;
            this.title = title;
            this.artist = artist;
            this.durationSeconds = durationSeconds;
            this.mimeType = mimeType;
            this.headersJson = headersJson;
        }
    }

    public static Result resolve(String videoId) throws Exception {
        if (videoId == null || videoId.trim().isEmpty()) {
            throw new IllegalArgumentException("videoId is required");
        }
        ensureInit();

        final String watchUrl = "https://www.youtube.com/watch?v=" + videoId.trim();
        Log.i(TAG, "Extracting audio for " + videoId);

        final StreamInfo info = StreamInfo.getInfo(ServiceList.YouTube, watchUrl);
        if (info.getStreamType() == StreamType.LIVE_STREAM
            || info.getStreamType() == StreamType.AUDIO_LIVE_STREAM) {
            throw new IllegalStateException("Live streams are not supported for background audio");
        }

        final List<AudioStream> audioStreams = info.getAudioStreams();
        if (audioStreams == null || audioStreams.isEmpty()) {
            throw new IllegalStateException("No audio streams found for this video");
        }

        final AudioStream best = audioStreams.stream()
            .max(Comparator
                .comparingInt(AudioStream::getAverageBitrate)
                .thenComparingInt(s -> preferFormatScore(s)))
            .orElseThrow(() -> new IllegalStateException("No usable audio stream"));

        final String contentUrl = best.getContent();
        if (contentUrl == null || contentUrl.isEmpty()) {
            throw new IllegalStateException("Audio stream has empty URL");
        }

        String mime = "audio/mp4";
        try {
            if (best.getFormat() != null && best.getFormat().getMimeType() != null) {
                mime = best.getFormat().getMimeType();
            }
        } catch (Exception ignored) {
            /* keep default */
        }

        // ExoPlayer uses a browser User-Agent in MediaPlaybackService; stream-specific
        // headers are optional and not exposed the same way across Extractor versions.
        final String headersJson = null;

        final String title = info.getName() != null ? info.getName() : "NoRepeat";
        final String artist = info.getUploaderName() != null ? info.getUploaderName() : "YouTube";
        final long duration = Math.max(0, info.getDuration());

        Log.i(TAG, "Resolved audio bitrate=" + best.getAverageBitrate() + " mime=" + mime);
        return new Result(contentUrl, title, artist, duration, mime, headersJson);
    }

    private static int preferFormatScore(AudioStream stream) {
        try {
            if (stream.getFormat() == null) return 0;
            String name = String.valueOf(stream.getFormat()).toLowerCase(Locale.US);
            if (name.contains("m4a") || name.contains("mp4")) return 100;
            if (name.contains("webm") || name.contains("opus")) return 50;
        } catch (Exception ignored) {
            /* ignore */
        }
        return 0;
    }
}
