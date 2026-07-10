package com.noverep.app;

import android.Manifest;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.webkit.WebSettings;
import android.webkit.WebView;

import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.BridgeActivity;

/**
 * Capacitor shell for NoRepeat.
 * Keeps the WebView media pipeline alive when the screen turns off.
 */
public class MainActivity extends BridgeActivity {
    private final BroadcastReceiver mediaActionReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (intent == null || intent.getAction() == null || bridge == null) return;
            String js;
            switch (intent.getAction()) {
                case MediaPlaybackService.ACTION_JS_PLAY:
                    js = "window.dispatchEvent(new CustomEvent('noverep-media',{detail:{action:'play'}}));";
                    break;
                case MediaPlaybackService.ACTION_JS_PAUSE:
                    js = "window.dispatchEvent(new CustomEvent('noverep-media',{detail:{action:'pause'}}));";
                    break;
                case MediaPlaybackService.ACTION_JS_NEXT:
                    js = "window.dispatchEvent(new CustomEvent('noverep-media',{detail:{action:'next'}}));";
                    break;
                case MediaPlaybackService.ACTION_JS_PREV:
                    js = "window.dispatchEvent(new CustomEvent('noverep-media',{detail:{action:'previous'}}));";
                    break;
                case MediaPlaybackService.ACTION_JS_ENDED:
                    js = "window.dispatchEvent(new CustomEvent('noverep-media',{detail:{action:'ended'}}));";
                    break;
                default:
                    return;
            }
            WebView webView = bridge.getWebView();
            if (webView == null) return;
            webView.post(() -> webView.evaluateJavascript(js, null));
        }
    };

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(BackgroundAudioPlugin.class);
        super.onCreate(savedInstanceState);
        configureWebView();
        requestNotificationPermission();
        maybeRequestBatteryExemption();
        registerMediaReceiver();
    }

    @Override
    public void onStart() {
        super.onStart();
        configureWebView();
        keepWebViewAlive();
    }

    @Override
    public void onResume() {
        super.onResume();
        keepWebViewAlive();
    }

    @Override
    public void onPause() {
        super.onPause();
        // Capacitor/Cordova may pause timers; immediately resume so YouTube can keep playing.
        keepWebViewAlive();
        injectResumePlayback();
    }

    @Override
    public void onStop() {
        super.onStop();
        keepWebViewAlive();
        injectResumePlayback();
    }

    @Override
    public void onDestroy() {
        try {
            unregisterReceiver(mediaActionReceiver);
        } catch (Exception ignored) {
        }
        super.onDestroy();
    }

    private void keepWebViewAlive() {
        if (bridge == null) return;
        WebView webView = bridge.getWebView();
        if (webView == null) return;
        try {
            webView.onResume();
            webView.resumeTimers();
        } catch (Exception ignored) {
        }
    }

    private void injectResumePlayback() {
        if (bridge == null || bridge.getWebView() == null) return;
        String js =
            "window.dispatchEvent(new CustomEvent('noverep-media',{detail:{action:'resume-background'}}));";
        bridge.getWebView().post(() -> {
            keepWebViewAlive();
            bridge.getWebView().evaluateJavascript(js, null);
        });
    }

    private void registerMediaReceiver() {
        IntentFilter filter = new IntentFilter();
        filter.addAction(MediaPlaybackService.ACTION_JS_PLAY);
        filter.addAction(MediaPlaybackService.ACTION_JS_PAUSE);
        filter.addAction(MediaPlaybackService.ACTION_JS_NEXT);
        filter.addAction(MediaPlaybackService.ACTION_JS_PREV);
        filter.addAction(MediaPlaybackService.ACTION_JS_ENDED);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(mediaActionReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(mediaActionReceiver, filter);
        }
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return;
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
            == PackageManager.PERMISSION_GRANTED) {
            return;
        }
        ActivityCompat.requestPermissions(
            this,
            new String[]{Manifest.permission.POST_NOTIFICATIONS},
            1001
        );
    }

    private void maybeRequestBatteryExemption() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return;
        try {
            PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
            String pkg = getPackageName();
            if (pm != null && !pm.isIgnoringBatteryOptimizations(pkg)) {
                Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                intent.setData(Uri.parse("package:" + pkg));
                startActivity(intent);
            }
        } catch (Exception ignored) {
            // Some OEMs block this intent; user can set Unrestricted manually.
        }
    }

    private void configureWebView() {
        if (this.bridge == null) return;
        WebView webView = this.bridge.getWebView();
        if (webView == null) return;

        WebSettings settings = webView.getSettings();
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setDomStorageEnabled(true);
        settings.setJavaScriptEnabled(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
    }
}
