package com.noverep.app;

import android.content.Intent;
import android.os.Build;
import android.util.Log;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@CapacitorPlugin(name = "BackgroundAudio")
public class BackgroundAudioPlugin extends Plugin {
    private static final String TAG = "BackgroundAudio";
    private final ExecutorService extractorExecutor = Executors.newSingleThreadExecutor();

    @PluginMethod
    public void syncQueue(PluginCall call) {
        try {
            JSArray raw = call.getArray("items");
            String currentVideoId = call.getString("currentVideoId", "");
            List<PlaybackQueueStore.Item> items = new ArrayList<>();
            if (raw != null) {
                JSONArray arr = raw;
                for (int i = 0; i < arr.length(); i++) {
                    JSONObject obj = arr.getJSONObject(i);
                    String videoId = obj.optString("videoId", "");
                    if (videoId.isEmpty()) continue;
                    items.add(new PlaybackQueueStore.Item(
                        videoId,
                        obj.optString("title", "NoRepeat"),
                        obj.optString("artist", "Playing"),
                        obj.optString("queueItemId", "")
                    ));
                }
            }
            PlaybackQueueStore.setQueue(items, currentVideoId);
            Log.i(TAG, "syncQueue size=" + items.size() + " current=" + currentVideoId);
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "syncQueue failed", e);
            call.reject("syncQueue failed: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void resolveAudioStream(PluginCall call) {
        String videoId = call.getString("videoId");
        if (videoId == null || videoId.isEmpty()) {
            call.reject("videoId is required");
            return;
        }

        extractorExecutor.execute(() -> {
            try {
                YoutubeStreamExtractor.Result result = YoutubeStreamExtractor.resolve(videoId);
                JSObject out = new JSObject();
                out.put("url", result.url);
                out.put("title", result.title);
                out.put("artist", result.artist);
                out.put("duration_seconds", result.durationSeconds);
                out.put("mime_type", result.mimeType);
                if (result.headersJson != null) {
                    out.put("headersJson", result.headersJson);
                }
                call.resolve(out);
            } catch (Exception e) {
                Log.e(TAG, "resolveAudioStream failed", e);
                call.reject("Client extract failed: " + e.getMessage(), e);
            }
        });
    }

    @PluginMethod
    public void playStream(PluginCall call) {
        String url = call.getString("url");
        if (url == null || url.isEmpty()) {
            call.reject("url is required");
            return;
        }
        String title = call.getString("title", "NoRepeat");
        String artist = call.getString("artist", "Playing");
        String videoId = call.getString("videoId", "");
        if (videoId != null && !videoId.isEmpty()) {
            PlaybackQueueStore.markCurrent(videoId);
        }

        Intent intent = new Intent(getContext(), MediaPlaybackService.class);
        intent.setAction(MediaPlaybackService.ACTION_PLAY);
        intent.putExtra(MediaPlaybackService.EXTRA_URL, url);
        intent.putExtra(MediaPlaybackService.EXTRA_TITLE, title);
        intent.putExtra(MediaPlaybackService.EXTRA_ARTIST, artist);
        if (videoId != null && !videoId.isEmpty()) {
            intent.putExtra(MediaPlaybackService.EXTRA_VIDEO_ID, videoId);
        }

        String headersJson = call.getString("headersJson");
        if (headersJson == null || headersJson.isEmpty()) {
            JSObject headers = call.getObject("headers");
            if (headers != null) {
                headersJson = headers.toString();
            }
        }
        if (headersJson != null && !headersJson.isEmpty()) {
            intent.putExtra(MediaPlaybackService.EXTRA_HEADERS_JSON, headersJson);
        }

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                getContext().startForegroundService(intent);
            } else {
                getContext().startService(intent);
            }
            call.resolve();
        } catch (Exception e) {
            Log.e(TAG, "playStream failed", e);
            call.reject("Failed to start playback service: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void pause(PluginCall call) {
        Intent intent = new Intent(getContext(), MediaPlaybackService.class);
        intent.setAction(MediaPlaybackService.ACTION_PAUSE);
        try {
            getContext().startService(intent);
            call.resolve();
        } catch (Exception e) {
            call.reject("pause failed: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void resume(PluginCall call) {
        Intent intent = new Intent(getContext(), MediaPlaybackService.class);
        intent.setAction(MediaPlaybackService.ACTION_RESUME);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                getContext().startForegroundService(intent);
            } else {
                getContext().startService(intent);
            }
            call.resolve();
        } catch (Exception e) {
            call.reject("resume failed: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void stop(PluginCall call) {
        Intent intent = new Intent(getContext(), MediaPlaybackService.class);
        intent.setAction(MediaPlaybackService.ACTION_STOP);
        try {
            getContext().startService(intent);
            call.resolve();
        } catch (Exception e) {
            call.reject("stop failed: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void seek(PluginCall call) {
        Double seconds = call.getDouble("seconds", 0.0);
        Intent intent = new Intent(getContext(), MediaPlaybackService.class);
        intent.setAction(MediaPlaybackService.ACTION_SEEK);
        intent.putExtra(MediaPlaybackService.EXTRA_POSITION_MS, (long) (seconds * 1000));
        try {
            getContext().startService(intent);
            call.resolve();
        } catch (Exception e) {
            call.reject("seek failed: " + e.getMessage(), e);
        }
    }

    @PluginMethod
    public void getStatus(PluginCall call) {
        JSObject status = new JSObject();
        status.put("playing", MediaPlaybackService.isPlayingNow());
        status.put("position", MediaPlaybackService.getPositionMs() / 1000.0);
        status.put("duration", MediaPlaybackService.getDurationMs() / 1000.0);
        call.resolve(status);
    }

    @PluginMethod
    public void start(PluginCall call) {
        call.resolve();
    }

    @PluginMethod
    public void update(PluginCall call) {
        Boolean playing = call.getBoolean("playing", true);
        if (Boolean.TRUE.equals(playing)) {
            resume(call);
        } else {
            pause(call);
        }
    }
}
