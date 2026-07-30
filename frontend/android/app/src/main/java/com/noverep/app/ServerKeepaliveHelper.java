package com.noverep.app;

import android.util.Log;

import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Best-effort HTTP pings to keep Render free-tier APIs awake.
 *
 * Used from the playback foreground service (no extra notification) and from
 * MainActivity while the app is in the foreground. Cannot run reliably when
 * the app is fully closed — Android Doze blocks that without a visible service.
 */
public final class ServerKeepaliveHelper {
    private static final String TAG = "NoRepeatKeepalive";
    private static final ExecutorService EXEC = Executors.newSingleThreadExecutor();

    private ServerKeepaliveHelper() {}

    public static void pingBothAsync() {
        EXEC.execute(ServerKeepaliveHelper::pingBothSync);
    }

    static void pingBothSync() {
        pingUrl(getApiHealthUrl());
        pingUrl(getSongsLibraryHealthUrl());
    }

    private static String getApiHealthUrl() {
        return BuildConfig.NOREP_API_HEALTH_URL;
    }

    private static String getSongsLibraryHealthUrl() {
        return BuildConfig.SONGS_LIBRARY_HEALTH_URL;
    }

    private static void pingUrl(String urlString) {
        if (urlString == null || urlString.isEmpty()) return;
        HttpURLConnection conn = null;
        try {
            URL url = new URL(urlString);
            conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(12_000);
            conn.setReadTimeout(12_000);
            conn.setRequestMethod("GET");
            conn.setRequestProperty("User-Agent", "NoRepeat-Android-Keepalive/1.0");
            int code = conn.getResponseCode();
            Log.d(TAG, "ping " + urlString + " -> " + code);
        } catch (Exception e) {
            Log.w(TAG, "ping failed " + urlString + ": " + e.getMessage());
        } finally {
            if (conn != null) conn.disconnect();
        }
    }
}
