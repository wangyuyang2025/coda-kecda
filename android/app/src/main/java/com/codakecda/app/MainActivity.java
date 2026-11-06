package com.codakecda.app;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslCertificate;
import android.net.http.SslError;
import android.os.Bundle;
import android.text.InputType;
import android.util.Base64;
import android.view.Gravity;
import android.view.ViewGroup;
import android.webkit.SslErrorHandler;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.URL;
import java.security.SecureRandom;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * 课达手机网页版的安卓外壳。课表和记录都在电脑上，这里只负责连上去。
 * 第一次连接时记下这台电脑的证书机构，以后只信它签的证书；之后用电脑上的 6 位数配对。
 */
public class MainActivity extends Activity {
    private static final int PORT = 18767;
    private SharedPreferences prefs;
    private WebView web;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        prefs = getSharedPreferences("coda", MODE_PRIVATE);
        if (prefs.getString("host", "").isEmpty() || prefs.getString("ca", "").isEmpty()) showSetup("");
        else openWeb();
    }

    private LinearLayout page() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER_VERTICAL);
        int pad = (int) (24 * getResources().getDisplayMetrics().density);
        box.setPadding(pad, pad, pad, pad);
        box.setBackgroundColor(Color.WHITE);
        return box;
    }

    private TextView text(String s, float size) {
        TextView v = new TextView(this);
        v.setText(s);
        v.setTextSize(size);
        v.setTextColor(Color.rgb(14, 23, 38));
        v.setPadding(0, 0, 0, 24);
        return v;
    }

    private void showSetup(String message) {
        web = null;
        LinearLayout box = page();
        box.addView(text("连接电脑上的课达", 24));
        box.addView(text("手机和电脑连同一个 Wi-Fi。在电脑课达的“服务管理”点“连接手机网页版”，把网址里的地址填到这里，比如 192.168.1.20", 16));
        final EditText input = new EditText(this);
        input.setHint("电脑地址");
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(prefs.getString("host", ""));
        box.addView(input);
        final TextView note = text(message, 15);
        note.setTextColor(Color.rgb(212, 88, 88));
        note.setPadding(0, 24, 0, 24);
        box.addView(note);
        final Button go = new Button(this);
        go.setText("连接");
        box.addView(go);
        go.setOnClickListener(v -> {
            final String host = cleanHost(input.getText().toString());
            if (host.isEmpty()) {
                note.setText("请填电脑地址");
                return;
            }
            go.setEnabled(false);
            note.setText("正在连接…");
            new Thread(() -> {
                try {
                    final byte[] der = fetchAuthority(host);
                    runOnUiThread(() -> {
                        prefs.edit().putString("host", host).putString("ca", Base64.encodeToString(der, Base64.NO_WRAP)).apply();
                        openWeb();
                    });
                } catch (Exception e) {
                    runOnUiThread(() -> {
                        go.setEnabled(true);
                        note.setText("连不上这台电脑。请确认地址对、电脑上的课达开着、两边在同一个 Wi-Fi。");
                    });
                }
            }).start();
        });
        setContentView(box);
    }

    static String cleanHost(String raw) {
        String s = raw.trim().replaceFirst("^[a-zA-Z]+://", "");
        int cut = s.indexOf('/');
        if (cut >= 0) s = s.substring(0, cut);
        cut = s.indexOf(':');
        if (cut >= 0) s = s.substring(0, cut);
        return s;
    }

    /** 第一次连接：还不认识这台电脑，先取回它的证书机构，以后只信它。 */
    private byte[] fetchAuthority(String host) throws Exception {
        TrustManager[] any = {new X509TrustManager() {
            @Override public void checkClientTrusted(X509Certificate[] c, String a) {}
            @Override public void checkServerTrusted(X509Certificate[] c, String a) {}
            @Override public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
        }};
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, any, new SecureRandom());
        HttpsURLConnection c = (HttpsURLConnection) new URL("https://" + host + ":" + PORT + "/m/cert").openConnection();
        c.setSSLSocketFactory(ctx.getSocketFactory());
        c.setHostnameVerifier((h, s) -> true);
        c.setConnectTimeout(6000);
        c.setReadTimeout(6000);
        try (InputStream in = c.getInputStream()) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
            X509Certificate ca = parse(out.toByteArray());
            ca.checkValidity();
            return ca.getEncoded();
        } finally {
            c.disconnect();
        }
    }

    private static X509Certificate parse(byte[] data) throws Exception {
        return (X509Certificate) CertificateFactory.getInstance("X.509").generateCertificate(new ByteArrayInputStream(data));
    }

    /** 网页的证书必须是记下的那个证书机构签的，别的一律不连。 */
    private boolean trusted(SslError error) {
        try {
            Bundle b = SslCertificate.saveState(error.getCertificate());
            X509Certificate leaf = parse(b.getByteArray("x509-certificate"));
            X509Certificate ca = parse(Base64.decode(prefs.getString("ca", ""), Base64.NO_WRAP));
            leaf.checkValidity();
            leaf.verify(ca.getPublicKey());
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private void openWeb() {
        final String host = prefs.getString("host", "");
        final String home = "https://" + host + ":" + PORT + "/m";
        web = new WebView(this);
        web.setLayoutParams(new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                if (trusted(error)) handler.proceed();
                else {
                    handler.cancel();
                    showSetup("这台电脑的证书和上次不一样，没有连接。如果换了电脑，请重新填地址。");
                    prefs.edit().remove("ca").apply();
                }
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if (host.equals(u.getHost())) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (Exception ignored) {
                }
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showOffline();
            }
        });
        setContentView(web);
        web.loadUrl(home);
    }

    private void showOffline() {
        web = null;
        LinearLayout box = page();
        box.addView(text("连不上电脑", 24));
        box.addView(text("请确认手机和电脑在同一个 Wi-Fi，电脑上的课达开着。", 16));
        Button retry = new Button(this);
        retry.setText("重试");
        retry.setOnClickListener(v -> openWeb());
        box.addView(retry);
        Button change = new Button(this);
        change.setText("改电脑地址");
        change.setOnClickListener(v -> showSetup(""));
        box.addView(change);
        setContentView(box);
    }

    @Override
    public void onBackPressed() {
        if (web == null) {
            super.onBackPressed();
            return;
        }
        // 菜单开着时，返回键只关菜单
        web.evaluateJavascript("(function(){var m=document.getElementById('menu');if(m&&!m.hidden){m.hidden=true;return 1}return 0})()", opened -> {
            if ("1".equals(opened)) return;
            if (web != null && web.canGoBack()) web.goBack();
            else MainActivity.super.onBackPressed();
        });
    }
}
