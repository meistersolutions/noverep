package com.noverep.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.support.v4.media.MediaMetadataCompat;
import android.support.v4.media.session.MediaSessionCompat;
import android.support.v4.media.session.PlaybackStateCompat;
import android.util.Log;
import android.view.KeyEvent;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import androidx.media.app.NotificationCompat.MediaStyle;
import androidx.media.session.MediaButtonReceiver;
import androidx.media3.common.AudioAttributes;
import androidx.media3.common.C;
import androidx.media3.common.MediaItem;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory;

import org.json.JSONObject;

import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * NewPipe-style background audio: ExoPlayer + foreground service + MediaSession
 * (car / Bluetooth skip, play, pause).
 */
public class MediaPlaybackService extends Service {
    private static final String TAG = "NoRepeatPlayback";
    public static final String CHANNEL_ID = "noverep_playback";
    public static final int NOTIFICATION_ID = 42;

    public static final String ACTION_PLAY = "com.noverep.app.PLAY_STREAM";
    public static final String ACTION_PAUSE = "com.noverep.app.PAUSE_STREAM";
    public static final String ACTION_RESUME = "com.noverep.app.RESUME_STREAM";
    public static final String ACTION_STOP = "com.noverep.app.STOP_STREAM";
    public static final String ACTION_SEEK = "com.noverep.app.SEEK_STREAM";
    public static final String ACTION_SKIP_NEXT = "com.noverep.app.SKIP_NEXT";
    public static final String ACTION_SKIP_PREV = "com.noverep.app.SKIP_PREV";

    public static final String EXTRA_URL = "url";
    public static final String EXTRA_TITLE = "title";
    public static final String EXTRA_ARTIST = "artist";
    public static final String EXTRA_HEADERS_JSON = "headers_json";
    public static final String EXTRA_POSITION_MS = "position_ms";

    public static final String ACTION_JS_PLAY = "com.noverep.app.JS_PLAY";
    public static final String ACTION_JS_PAUSE = "com.noverep.app.JS_PAUSE";
    public static final String ACTION_JS_NEXT = "com.noverep.app.JS_NEXT";
    public static final String ACTION_JS_PREV = "com.noverep.app.JS_PREV";
    public static final String ACTION_JS_ENDED = "com.noverep.app.JS_ENDED";
    public static final String ACTION_JS_ERROR = "com.noverep.app.JS_ERROR";
    public static final String ACTION_JS_TRACK_CHANGED = "com.noverep.app.JS_TRACK_CHANGED";
    public static final String EXTRA_VIDEO_ID = "video_id";
    public static final String EXTRA_QUEUE_ITEM_ID = "queue_item_id";
    public static final String EXTRA_REASON = "reason"; // next | previous | ended
    public static final String EXTRA_PREV_VIDEO_ID = "prev_video_id";
    public static final String EXTRA_PREV_POSITION_MS = "prev_position_ms";
    public static final String EXTRA_PREV_DURATION_MS = "prev_duration_ms";

    private static final String DEFAULT_UA =
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36";

    private static final long MEDIA_ACTIONS =
        PlaybackStateCompat.ACTION_PLAY
            | PlaybackStateCompat.ACTION_PAUSE
            | PlaybackStateCompat.ACTION_PLAY_PAUSE
            | PlaybackStateCompat.ACTION_STOP
            | PlaybackStateCompat.ACTION_SKIP_TO_NEXT
            | PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS
            | PlaybackStateCompat.ACTION_SEEK_TO;

    private static ExoPlayer player;
    private static String currentTitle = "NoRepeat";
    private static String currentArtist = "Playing";
    private static final AtomicBoolean playingFlag = new AtomicBoolean(false);
    private static final AtomicLong positionMs = new AtomicLong(0);
    private static final AtomicLong durationMs = new AtomicLong(0);
    private static final AtomicBoolean advancing = new AtomicBoolean(false);

    private PowerManager.WakeLock wakeLock;
    private MediaSessionCompat mediaSession;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final java.util.concurrent.ExecutorService extractExecutor =
        java.util.concurrent.Executors.newSingleThreadExecutor();
    private final Runnable positionTicker = new Runnable() {
        @Override
        public void run() {
            syncClockFromPlayer();
            updateMediaSessionState();
            if (playingFlag.get()) {
                mainHandler.postDelayed(this, 500);
            }
        }
    };

    public static boolean isPlayingNow() {
        return playingFlag.get();
    }

    public static long getPositionMs() {
        return positionMs.get();
    }

    public static long getDurationMs() {
        return durationMs.get();
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "noverep:exo");
        wakeLock.setReferenceCounted(false);
        initMediaSession();
    }

    private void initMediaSession() {
        mediaSession = new MediaSessionCompat(this, "NoRepeat");
        mediaSession.setFlags(
            MediaSessionCompat.FLAG_HANDLES_MEDIA_BUTTONS
                | MediaSessionCompat.FLAG_HANDLES_TRANSPORT_CONTROLS
        );
        mediaSession.setCallback(new MediaSessionCompat.Callback() {
            @Override
            public void onPlay() {
                resumePlayback();
                sendBroadcast(new Intent(ACTION_JS_PLAY).setPackage(getPackageName()));
            }

            @Override
            public void onPause() {
                pausePlayback();
                sendBroadcast(new Intent(ACTION_JS_PAUSE).setPackage(getPackageName()));
            }

            @Override
            public void onStop() {
                stopPlayback();
                stopSelf();
            }

            @Override
            public void onSkipToNext() {
                playAdjacentFromQueue(true, "next");
            }

            @Override
            public void onSkipToPrevious() {
                playAdjacentFromQueue(false, "previous");
            }

            @Override
            public void onSeekTo(long pos) {
                mainHandler.post(() -> {
                    if (player != null) {
                        player.seekTo(pos);
                        positionMs.set(pos);
                        updateMediaSessionState();
                    }
                });
            }

            @Override
            public boolean onMediaButtonEvent(Intent mediaButtonEvent) {
                KeyEvent event = mediaButtonEvent.getParcelableExtra(Intent.EXTRA_KEY_EVENT);
                if (event != null
                    && event.getAction() == KeyEvent.ACTION_DOWN
                    && event.getRepeatCount() == 0) {
                    switch (event.getKeyCode()) {
                        case KeyEvent.KEYCODE_MEDIA_NEXT:
                            onSkipToNext();
                            return true;
                        case KeyEvent.KEYCODE_MEDIA_PREVIOUS:
                            onSkipToPrevious();
                            return true;
                        case KeyEvent.KEYCODE_MEDIA_PLAY:
                            onPlay();
                            return true;
                        case KeyEvent.KEYCODE_MEDIA_PAUSE:
                            onPause();
                            return true;
                        case KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE:
                        case KeyEvent.KEYCODE_HEADSETHOOK:
                            if (playingFlag.get()) onPause();
                            else onPlay();
                            return true;
                        default:
                            break;
                    }
                }
                return super.onMediaButtonEvent(mediaButtonEvent);
            }
        });

        Intent launch = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (launch != null) {
            PendingIntent pi = PendingIntent.getActivity(
                this,
                0,
                launch,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
            );
            mediaSession.setSessionActivity(pi);
        }

        Intent mediaButtonIntent = new Intent(Intent.ACTION_MEDIA_BUTTON, null, this, MediaButtonReceiver.class);
        PendingIntent mbr = PendingIntent.getBroadcast(
            this,
            0,
            mediaButtonIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        mediaSession.setMediaButtonReceiver(mbr);

        mediaSession.setActive(true);
        updateMediaSessionMetadata();
        updateMediaSessionState();
    }

    private void updateMediaSessionMetadata() {
        if (mediaSession == null) return;
        MediaMetadataCompat.Builder meta = new MediaMetadataCompat.Builder()
            .putString(MediaMetadataCompat.METADATA_KEY_TITLE, currentTitle)
            .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, currentArtist)
            .putString(MediaMetadataCompat.METADATA_KEY_DISPLAY_TITLE, currentTitle)
            .putString(MediaMetadataCompat.METADATA_KEY_DISPLAY_SUBTITLE, currentArtist);
        long duration = durationMs.get();
        if (duration > 0) {
            meta.putLong(MediaMetadataCompat.METADATA_KEY_DURATION, duration);
        }
        mediaSession.setMetadata(meta.build());
    }

    private void updateMediaSessionState() {
        if (mediaSession == null) return;
        int state = playingFlag.get()
            ? PlaybackStateCompat.STATE_PLAYING
            : PlaybackStateCompat.STATE_PAUSED;
        PlaybackStateCompat playbackState = new PlaybackStateCompat.Builder()
            .setActions(MEDIA_ACTIONS)
            .setState(state, positionMs.get(), playingFlag.get() ? 1.0f : 0f)
            .build();
        mediaSession.setPlaybackState(playbackState);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        promoteForeground();

        if (intent == null) {
            return START_STICKY;
        }

        if (Intent.ACTION_MEDIA_BUTTON.equals(intent.getAction())) {
            MediaButtonReceiver.handleIntent(mediaSession, intent);
            return START_STICKY;
        }

        String action = intent.getAction();
        if (ACTION_STOP.equals(action)) {
            stopPlayback();
            stopSelf();
            return START_NOT_STICKY;
        }
        if (ACTION_PAUSE.equals(action)) {
            pausePlayback();
            return START_STICKY;
        }
        if (ACTION_RESUME.equals(action)) {
            resumePlayback();
            return START_STICKY;
        }
        if (ACTION_SKIP_NEXT.equals(action)) {
            playAdjacentFromQueue(true, "next");
            return START_STICKY;
        }
        if (ACTION_SKIP_PREV.equals(action)) {
            playAdjacentFromQueue(false, "previous");
            return START_STICKY;
        }
        if (ACTION_SEEK.equals(action)) {
            long pos = intent.getLongExtra(EXTRA_POSITION_MS, 0L);
            mainHandler.post(() -> {
                if (player != null) {
                    player.seekTo(pos);
                    positionMs.set(pos);
                    updateMediaSessionState();
                }
            });
            return START_STICKY;
        }

        String url = intent.getStringExtra(EXTRA_URL);
        if (url != null && !url.isEmpty()) {
            currentTitle = intent.getStringExtra(EXTRA_TITLE);
            if (currentTitle == null) currentTitle = "NoRepeat";
            currentArtist = intent.getStringExtra(EXTRA_ARTIST);
            if (currentArtist == null) currentArtist = "Playing";
            String headersJson = intent.getStringExtra(EXTRA_HEADERS_JSON);
            startPlayback(url, parseHeaders(headersJson));
        }

        return START_STICKY;
    }

    private void playAdjacentFromQueue(boolean next, String reason) {
        if (!advancing.compareAndSet(false, true)) {
            Log.i(TAG, "Skip ignored — already advancing");
            return;
        }
        extractExecutor.execute(() -> {
            try {
                PlaybackQueueStore.Item previous = PlaybackQueueStore.current();
                long prevPosMs = positionMs.get();
                long prevDurMs = durationMs.get();
                String prevVideoId = previous != null ? previous.videoId : "";

                PlaybackQueueStore.Item item = next
                    ? PlaybackQueueStore.advanceNext()
                    : PlaybackQueueStore.advancePrevious();
                if (item == null) {
                    Log.i(TAG, "No more tracks in native queue (" + reason + ")");
                    // Fall back to JS so discovery can fetch more.
                    String fallback = next ? ACTION_JS_NEXT : ACTION_JS_PREV;
                    if ("ended".equals(reason)) fallback = ACTION_JS_ENDED;
                    sendBroadcast(new Intent(fallback).setPackage(getPackageName()));
                    return;
                }

                Log.i(TAG, "Native queue " + reason + " → " + item.videoId);
                YoutubeStreamExtractor.Result stream = YoutubeStreamExtractor.resolve(item.videoId);
                boolean weakTitle = item.title == null || item.title.isEmpty()
                    || "NoRepeat".equals(item.title);
                boolean weakArtist = item.artist == null || item.artist.isEmpty()
                    || "Playing".equals(item.artist);
                currentTitle = !weakTitle ? item.title : (stream.title != null ? stream.title : item.title);
                currentArtist = !weakArtist ? item.artist : (stream.artist != null ? stream.artist : item.artist);
                startPlayback(stream.url, parseHeaders(stream.headersJson));
                notifyTrackChanged(
                    item.videoId,
                    currentTitle,
                    currentArtist,
                    item.queueItemId,
                    reason,
                    prevVideoId,
                    prevPosMs,
                    prevDurMs
                );
            } catch (Exception e) {
                Log.e(TAG, "Native queue advance failed", e);
                sendBroadcast(new Intent(ACTION_JS_ERROR).setPackage(getPackageName()));
            } finally {
                advancing.set(false);
            }
        });
    }

    private void notifyTrackChanged(
        String videoId,
        String title,
        String artist,
        String queueItemId,
        String reason,
        String prevVideoId,
        long prevPositionMs,
        long prevDurationMs
    ) {
        Intent intent = new Intent(ACTION_JS_TRACK_CHANGED).setPackage(getPackageName());
        intent.putExtra(EXTRA_VIDEO_ID, videoId);
        intent.putExtra(EXTRA_TITLE, title != null ? title : "NoRepeat");
        intent.putExtra(EXTRA_ARTIST, artist != null ? artist : "Playing");
        intent.putExtra(EXTRA_QUEUE_ITEM_ID, queueItemId != null ? queueItemId : "");
        intent.putExtra(EXTRA_REASON, reason);
        intent.putExtra(EXTRA_PREV_VIDEO_ID, prevVideoId != null ? prevVideoId : "");
        intent.putExtra(EXTRA_PREV_POSITION_MS, prevPositionMs);
        intent.putExtra(EXTRA_PREV_DURATION_MS, prevDurationMs);
        sendBroadcast(intent);
    }

    private Map<String, String> parseHeaders(String headersJson) {
        Map<String, String> headers = new HashMap<>();
        headers.put("User-Agent", DEFAULT_UA);
        headers.put("Accept", "*/*");
        headers.put("Accept-Language", "en-US,en;q=0.9");
        if (headersJson == null || headersJson.isEmpty()) {
            return headers;
        }
        try {
            JSONObject obj = new JSONObject(headersJson);
            Iterator<String> keys = obj.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                String value = obj.optString(key, null);
                if (value != null && !value.isEmpty()) {
                    headers.put(key, value);
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "Failed to parse stream headers", e);
        }
        if (!headers.containsKey("User-Agent") && !headers.containsKey("user-agent")) {
            headers.put("User-Agent", DEFAULT_UA);
        }
        return headers;
    }

    private void startPlayback(String url, Map<String, String> headers) {
        mainHandler.post(() -> {
            mainHandler.removeCallbacks(positionTicker);
            if (player != null) {
                player.stop();
                player.release();
                player = null;
            }
            positionMs.set(0);
            durationMs.set(0);
            ensurePlayer(headers);
            player.setMediaItem(MediaItem.fromUri(url));
            player.prepare();
            player.play();
            playingFlag.set(true);
            if (wakeLock != null && !wakeLock.isHeld()) {
                wakeLock.acquire(6 * 60 * 60 * 1000L);
            }
            updateMediaSessionMetadata();
            updateMediaSessionState();
            mainHandler.post(positionTicker);
            promoteForeground();
        });
    }

    private void pausePlayback() {
        mainHandler.post(() -> {
            if (player != null) player.pause();
            playingFlag.set(false);
            mainHandler.removeCallbacks(positionTicker);
            syncClockFromPlayer();
            updateMediaSessionState();
            promoteForeground();
        });
    }

    private void resumePlayback() {
        mainHandler.post(() -> {
            if (player != null) {
                player.play();
                playingFlag.set(true);
                mainHandler.removeCallbacks(positionTicker);
                mainHandler.post(positionTicker);
                updateMediaSessionState();
                promoteForeground();
            }
        });
    }

    private void stopPlayback() {
        mainHandler.post(() -> {
            mainHandler.removeCallbacks(positionTicker);
            if (player != null) {
                player.stop();
                player.release();
                player = null;
            }
            playingFlag.set(false);
            positionMs.set(0);
            durationMs.set(0);
            updateMediaSessionState();
            if (wakeLock != null && wakeLock.isHeld()) {
                wakeLock.release();
            }
            stopForeground(STOP_FOREGROUND_REMOVE);
        });
    }

    private void syncClockFromPlayer() {
        if (player == null) return;
        try {
            positionMs.set(Math.max(0, player.getCurrentPosition()));
            long d = player.getDuration();
            if (d > 0) durationMs.set(d);
            playingFlag.set(player.isPlaying());
        } catch (Exception e) {
            Log.w(TAG, "syncClockFromPlayer failed", e);
        }
    }

    private void ensurePlayer(Map<String, String> headers) {
        if (player != null) return;

        DefaultHttpDataSource.Factory httpFactory = new DefaultHttpDataSource.Factory()
            .setUserAgent(headers.getOrDefault("User-Agent", DEFAULT_UA))
            .setAllowCrossProtocolRedirects(true)
            .setConnectTimeoutMs(20_000)
            .setReadTimeoutMs(20_000)
            .setDefaultRequestProperties(headers);

        player = new ExoPlayer.Builder(this)
            .setMediaSourceFactory(new DefaultMediaSourceFactory(httpFactory))
            .build();

        AudioAttributes audioAttributes = new AudioAttributes.Builder()
            .setUsage(C.USAGE_MEDIA)
            .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
            .build();
        player.setAudioAttributes(audioAttributes, true);
        player.setHandleAudioBecomingNoisy(true);
        player.setWakeMode(C.WAKE_MODE_NETWORK);

        player.addListener(new Player.Listener() {
            @Override
            public void onPlaybackStateChanged(int playbackState) {
                syncClockFromPlayer();
                updateMediaSessionMetadata();
                updateMediaSessionState();
                if (playbackState == Player.STATE_ENDED) {
                    playingFlag.set(false);
                    mainHandler.removeCallbacks(positionTicker);
                    updateMediaSessionState();
                    // Advance natively — WebView may be suspended in background.
                    playAdjacentFromQueue(true, "ended");
                }
            }

            @Override
            public void onIsPlayingChanged(boolean playing) {
                playingFlag.set(playing);
                syncClockFromPlayer();
                updateMediaSessionState();
                if (playing) {
                    mainHandler.removeCallbacks(positionTicker);
                    mainHandler.post(positionTicker);
                }
                promoteForeground();
            }

            @Override
            public void onPlayerError(PlaybackException error) {
                Log.e(TAG, "ExoPlayer error: " + error.getMessage(), error);
                playingFlag.set(false);
                mainHandler.removeCallbacks(positionTicker);
                updateMediaSessionState();
                promoteForeground();
                sendBroadcast(new Intent(ACTION_JS_ERROR).setPackage(getPackageName()));
            }
        });
    }

    private void promoteForeground() {
        Notification notification = buildNotification();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
            );
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.notify(NOTIFICATION_ID, notification);
    }

    private Notification buildNotification() {
        Intent launch = getPackageManager().getLaunchIntentForPackage(getPackageName());
        PendingIntent contentIntent = PendingIntent.getActivity(
            this,
            0,
            launch,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        boolean playing = playingFlag.get();
        PendingIntent playPause = PendingIntent.getService(
            this,
            1,
            new Intent(this, MediaPlaybackService.class)
                .setAction(playing ? ACTION_PAUSE : ACTION_RESUME),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        PendingIntent next = PendingIntent.getService(
            this,
            2,
            new Intent(this, MediaPlaybackService.class).setAction(ACTION_SKIP_NEXT),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        PendingIntent prev = PendingIntent.getService(
            this,
            3,
            new Intent(this, MediaPlaybackService.class).setAction(ACTION_SKIP_PREV),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        int playPauseIcon = playing
            ? android.R.drawable.ic_media_pause
            : android.R.drawable.ic_media_play;

        MediaStyle style = new MediaStyle().setShowActionsInCompactView(0, 1, 2);
        if (mediaSession != null) {
            style.setMediaSession(mediaSession.getSessionToken());
        }

        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(currentTitle)
            .setContentText(currentArtist)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentIntent(contentIntent)
            .setOngoing(playing)
            .setOnlyAlertOnce(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setCategory(NotificationCompat.CATEGORY_TRANSPORT)
            .setStyle(style)
            .addAction(android.R.drawable.ic_media_previous, "Previous", prev)
            .addAction(playPauseIcon, playing ? "Pause" : "Play", playPause)
            .addAction(android.R.drawable.ic_media_next, "Next", next)
            .build();
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "NoRepeat Playback",
            NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription("Background audio playback");
        channel.setShowBadge(false);
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.createNotificationChannel(channel);
    }

    @Override
    public void onDestroy() {
        stopPlayback();
        extractExecutor.shutdownNow();
        if (mediaSession != null) {
            mediaSession.setActive(false);
            mediaSession.release();
            mediaSession = null;
        }
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
