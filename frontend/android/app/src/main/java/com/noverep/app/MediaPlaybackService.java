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
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import androidx.media.app.NotificationCompat.MediaStyle;
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
 * NewPipe-style background audio: ExoPlayer + foreground service.
 * Plays a direct audio stream URL (from yt-dlp), not a YouTube WebView iframe.
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

    private static final String DEFAULT_UA =
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36";

    private static ExoPlayer player;
    private static String currentTitle = "NoRepeat";
    private static String currentArtist = "Playing";
    private static final AtomicBoolean playingFlag = new AtomicBoolean(false);
    private static final AtomicLong positionMs = new AtomicLong(0);
    private static final AtomicLong durationMs = new AtomicLong(0);

    private PowerManager.WakeLock wakeLock;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final Runnable positionTicker = new Runnable() {
        @Override
        public void run() {
            syncClockFromPlayer();
            if (playingFlag.get()) {
                mainHandler.postDelayed(this, 250);
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
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // Must call startForeground promptly on Android 8+.
        promoteForeground();

        if (intent == null) {
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
        if (ACTION_SEEK.equals(action)) {
            long pos = intent.getLongExtra(EXTRA_POSITION_MS, 0L);
            mainHandler.post(() -> {
                if (player != null) {
                    player.seekTo(pos);
                    positionMs.set(pos);
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
                if (playbackState == Player.STATE_ENDED) {
                    playingFlag.set(false);
                    mainHandler.removeCallbacks(positionTicker);
                    sendBroadcast(new Intent(ACTION_JS_ENDED).setPackage(getPackageName()));
                    promoteForeground();
                }
            }

            @Override
            public void onIsPlayingChanged(boolean playing) {
                playingFlag.set(playing);
                syncClockFromPlayer();
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
        PendingIntent next = PendingIntent.getBroadcast(
            this,
            2,
            new Intent(ACTION_JS_NEXT).setPackage(getPackageName()),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        PendingIntent prev = PendingIntent.getBroadcast(
            this,
            3,
            new Intent(ACTION_JS_PREV).setPackage(getPackageName()),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        int playPauseIcon = playing
            ? android.R.drawable.ic_media_pause
            : android.R.drawable.ic_media_play;

        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(currentTitle)
            .setContentText(currentArtist)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentIntent(contentIntent)
            .setOngoing(playing)
            .setOnlyAlertOnce(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setCategory(NotificationCompat.CATEGORY_TRANSPORT)
            .setStyle(new MediaStyle().setShowActionsInCompactView(0, 1, 2))
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
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
