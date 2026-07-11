package com.noverep.app;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import org.schabi.newpipe.extractor.downloader.Downloader;
import org.schabi.newpipe.extractor.downloader.Request;
import org.schabi.newpipe.extractor.downloader.Response;
import org.schabi.newpipe.extractor.exceptions.ReCaptchaException;

import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;
import okhttp3.RequestBody;
import okhttp3.ResponseBody;

/**
 * Minimal OkHttp-backed downloader for NewPipe Extractor (client-side YouTube extraction).
 */
public final class OkHttpDownloader extends Downloader {
    private static final String USER_AGENT =
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0";

    private static OkHttpDownloader instance;
    private final OkHttpClient client;

    private OkHttpDownloader() {
        client = new OkHttpClient.Builder()
            .readTimeout(30, TimeUnit.SECONDS)
            .connectTimeout(20, TimeUnit.SECONDS)
            .followRedirects(true)
            .followSslRedirects(true)
            .build();
    }

    public static synchronized OkHttpDownloader getInstance() {
        if (instance == null) {
            instance = new OkHttpDownloader();
        }
        return instance;
    }

    @Override
    public Response execute(@NonNull final Request request) throws IOException, ReCaptchaException {
        final String httpMethod = request.httpMethod();
        final String url = request.url();
        final Map<String, List<String>> headers = request.headers();
        final byte[] dataToSend = request.dataToSend();

        RequestBody requestBody = null;
        if (dataToSend != null) {
            requestBody = RequestBody.create(dataToSend);
        }

        final okhttp3.Request.Builder requestBuilder = new okhttp3.Request.Builder()
            .method(httpMethod, requestBody)
            .url(url)
            .header("User-Agent", USER_AGENT);

        if (headers != null) {
            for (Map.Entry<String, List<String>> entry : headers.entrySet()) {
                final String name = entry.getKey();
                requestBuilder.removeHeader(name);
                for (String value : entry.getValue()) {
                    requestBuilder.addHeader(name, value);
                }
            }
        }

        try (okhttp3.Response response = client.newCall(requestBuilder.build()).execute()) {
            if (response.code() == 429) {
                throw new ReCaptchaException("reCaptcha Challenge requested", url);
            }

            String responseBodyToReturn = null;
            try (ResponseBody body = response.body()) {
                if (body != null) {
                    responseBodyToReturn = body.string();
                }
            }

            final String latestUrl = response.request().url().toString();
            return new Response(
                response.code(),
                response.message(),
                response.headers().toMultimap(),
                responseBodyToReturn,
                latestUrl
            );
        }
    }
}
