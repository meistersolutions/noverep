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

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import androidx.media3.common.MediaItem;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.exoplayer.ExoPlayer;

/**
 * NewPipe-style background audio: ExoPlayer + foreground service.
 * Plays a direct audio stream URL (from yt-dlp), not a YouTube WebView iframe.
 */
public class MediaPlaybackService extends Service {
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
    public static final String EXTRA_POSITION_MS = "position_ms";

    public static final String ACTION_JS_PLAY = "com.noverep.app.JS_PLAY";
    public static final String ACTION_JS_PAUSE = "com.noverep.app.JS_PAUSE";
    public static final String ACTION_JS_NEXT = "com.noverep.app.JS_NEXT";
    public static final String ACTION_JS_PREV = "com.noverep.app.JS_PREV";
    public static final String ACTION_JS_ENDED = "com.noverep.app.JS_ENDED";

    private static ExoPlayer player;
    private static String currentTitle = "NoRepeat";
    private static String currentArtist = "Playing";
    private static boolean isPlaying;

    private PowerManager.WakeLock wakeLock;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public static boolean isPlayingNow() {
        return isPlaying && player != null && player.isPlaying();
    }

    public static long getPositionMs() {
        return player != null ? player.getCurrentPosition() : 0L;
    }

    public static long getDurationMs() {
        if (player == null) return 0L;
        long d = player.getDuration();
        return d < 0 ? 0L : d;
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
            if (player != null) player.seekTo(pos);
            return START_STICKY;
        }

        String url = intent.getStringExtra(EXTRA_URL);
        if (url != null && !url.isEmpty()) {
            currentTitle = intent.getStringExtra(EXTRA_TITLE);
            if (currentTitle == null) currentTitle = "NoRepeat";
            currentArtist = intent.getStringExtra(EXTRA_ARTIST);
            if (currentArtist == null) currentArtist = "Playing";
            startPlayback(url);
        }

        promoteForeground();
        return START_STICKY;
    }

    private void startPlayback(String url) {
        mainHandler.post(() -> {
            ensurePlayer();
            player.stop();
            player.clearMediaItems();
            player.setMediaItem(MediaItem.fromUri(url));
            player.prepare();
            player.play();
            isPlaying = true;
            if (wakeLock != null && !wakeLock.isHeld()) {
                wakeLock.acquire(6 * 60 * 60 * 1000L);
            }
            promoteForeground();
        });
    }

    private void pausePlayback() {
        mainHandler.post(() -> {
            if (player != null) player.pause();
            isPlaying = false;
            promoteForeground();
        });
    }

    private void resumePlayback() {
        mainHandler.post(() -> {
            if (player != null) {
                player.play();
                isPlaying = true;
                promoteForeground();
            }
        });
    }

    private void stopPlayback() {
        mainHandler.post(() -> {
            if (player != null) {
                player.stop();
                player.release();
                player = null;
            }
            isPlaying = false;
            if (wakeLock != null && wakeLock.isHeld()) {
                wakeLock.release();
            }
            stopForeground(STOP_FOREGROUND_REMOVE);
        });
    }

    private void ensurePlayer() {
        if (player != null) return;
        player = new ExoPlayer.Builder(this).build();
        player.addListener(new Player.Listener() {
            @Override
            public void onPlaybackStateChanged(int playbackState) {
                if (playbackState == Player.STATE_ENDED) {
                    isPlaying = false;
                    sendBroadcast(new Intent(ACTION_JS_ENDED).setPackage(getPackageName()));
                    promoteForeground();
                }
            }

            @Override
            public void onIsPlayingChanged(boolean playing) {
                isPlaying = playing;
                promoteForeground();
            }

            @Override
            public void onPlayerError(PlaybackException error) {
                isPlaying = false;
                promoteForeground();
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

        PendingIntent playPause = PendingIntent.getService(
            this,
            1,
            new Intent(this, MediaPlaybackService.class)
                .setAction(isPlaying ? ACTION_PAUSE : ACTION_RESUME),
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

        int playPauseIcon = isPlaying
            ? android.R.drawable.ic_media_pause
            : android.R.drawable.ic_media_play;

        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(currentTitle)
            .setContentText(currentArtist)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentIntent(contentIntent)
            .setOngoing(isPlaying)
            .setOnlyAlertOnce(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setCategory(NotificationCompat.CATEGORY_TRANSPORT)
            .addAction(android.R.drawable.ic_media_previous, "Previous", prev)
            .addAction(playPauseIcon, isPlaying ? "Pause" : "Play", playPause)
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
