package com.workbench.mobile;

import android.annotation.SuppressLint;
import android.content.SharedPreferences;
import android.net.http.SslError;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.Toast;

import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;

/**
 * 视频工作台 · 手机端 WebView 壳。
 *
 * 通过 Tailscale 内网地址访问电脑上的视频工作台。
 * 默认地址 http://100.68.53.62:8089/ （电脑 Tailscale IP）。
 * 右上角菜单可修改服务器地址 / 刷新 / 退出。
 */
public class MainActivity extends AppCompatActivity {

    private WebView webView;
    private ProgressBar progressBar;
    private SharedPreferences prefs;
    private static final String PREF_URL = "server_url";
    private static final String DEFAULT_URL = "http://100.68.53.62:8089/";

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        prefs = getSharedPreferences("workbench", MODE_PRIVATE);
        String url = prefs.getString(PREF_URL, DEFAULT_URL);

        webView = findViewById(R.id.webview);
        progressBar = findViewById(R.id.progress_bar);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setSupportZoom(true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                progressBar.setVisibility(View.VISIBLE);
                progressBar.setProgress(0);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progressBar.setVisibility(View.GONE);
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                // 保持在同一 WebView 内导航
                view.loadUrl(url);
                return true;
            }

            @Override
            public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                // Tailscale 内网通常为 HTTP；若用到自签 HTTPS 可放开。生产建议按需处理。
                handler.proceed();
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
            }
        });

        webView.loadUrl(url);
    }

    // 返回键：优先回退网页历史
    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView != null && webView.canGoBack()) {
            webView.goBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    // 右上角菜单
    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, 1, 0, "修改服务器地址");
        menu.add(0, 2, 1, "刷新页面");
        menu.add(0, 3, 2, "退出");
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        switch (item.getItemId()) {
            case 1:
                editServerUrl();
                return true;
            case 2:
                webView.reload();
                return true;
            case 3:
                finish();
                return true;
            default:
                return super.onOptionsItemSelected(item);
        }
    }

    private void editServerUrl() {
        final EditText input = new EditText(this);
        String cur = webView.getUrl();
        input.setText(cur == null ? DEFAULT_URL : cur);
        input.setSingleLine(true);
        new AlertDialog.Builder(this)
                .setTitle("修改服务器地址")
                .setMessage("例如：http://100.68.53.62:8089/")
                .setView(input)
                .setPositiveButton("确定", (d, w) -> {
                    String url = input.getText().toString().trim();
                    if (url.isEmpty()) return;
                    if (!url.startsWith("http")) url = "http://" + url;
                    prefs.edit().putString(PREF_URL, url).apply();
                    webView.loadUrl(url);
                    Toast.makeText(this, "已切换到 " + url, Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("取消", null)
                .show();
    }
}
