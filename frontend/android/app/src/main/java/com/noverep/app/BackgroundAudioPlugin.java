package com.noverep.app;

import android.content.Intent;
import android.os.Build;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "BackgroundAudio")
public class BackgroundAudioPlugin extends Plugin {

    @PluginMethod
    public void playStream(PluginCall call) {
        String url = call.getString("url");
        if (url == null || url.isEmpty()) {
            call.reject("url is required");
            return;
        }
        String title = call.getString("title", "NoRepeat");
        String artist = call.getString("artist", "Playing");

        Intent intent = new Intent(getContext(), MediaPlaybackService.class);
        intent.setAction(MediaPlaybackService.ACTION_PLAY);
        intent.putExtra(MediaPlaybackService.EXTRA_URL, url);
        intent.putExtra(MediaPlaybackService.EXTRA_TITLE, title);
        intent.putExtra(MediaPlaybackService.EXTRA_ARTIST, artist);

        JSObject headers = call.getObject("headers");
        if (headers != null) {
            intent.putExtra(MediaPlaybackService.EXTRA_HEADERS_JSON, headers.toString());
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getContext().startForegroundService(intent);
        } else {
            getContext().startService(intent);
        }
        call.resolve();
    }

    @PluginMethod
    public void pause(PluginCall call) {
        Intent intent = new Intent(getContext(), MediaPlaybackService.class);
        intent.setAction(MediaPlaybackService.ACTION_PAUSE);
        getContext().startService(intent);
        call.resolve();
    }

    @PluginMethod
    public void resume(PluginCall call) {
        Intent intent = new Intent(getContext(), MediaPlaybackService.class);
        intent.setAction(MediaPlaybackService.ACTION_RESUME);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getContext().startForegroundService(intent);
        } else {
            getContext().startService(intent);
        }
        call.resolve();
    }

    @PluginMethod
    public void stop(PluginCall call) {
        Intent intent = new Intent(getContext(), MediaPlaybackService.class);
        intent.setAction(MediaPlaybackService.ACTION_STOP);
        getContext().startService(intent);
        call.resolve();
    }

    @PluginMethod
    public void seek(PluginCall call) {
        Double seconds = call.getDouble("seconds", 0.0);
        Intent intent = new Intent(getContext(), MediaPlaybackService.class);
        intent.setAction(MediaPlaybackService.ACTION_SEEK);
        intent.putExtra(MediaPlaybackService.EXTRA_POSITION_MS, (long) (seconds * 1000));
        getContext().startService(intent);
        call.resolve();
    }

    @PluginMethod
    public void getStatus(PluginCall call) {
        JSObject status = new JSObject();
        status.put("playing", MediaPlaybackService.isPlayingNow());
        status.put("position", MediaPlaybackService.getPositionMs() / 1000.0);
        status.put("duration", MediaPlaybackService.getDurationMs() / 1000.0);
        call.resolve(status);
    }

    // Kept for older JS callers; maps to playStream metadata-only no-op if no url.
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
