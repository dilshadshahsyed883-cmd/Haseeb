package pk.procuremate.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.*;
import android.database.Cursor;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.*;
import android.provider.OpenableColumns;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.*;
import android.graphics.pdf.PdfRenderer;

public class MainActivity extends Activity {
    private final int NAVY=Color.rgb(20,38,65), TEAL=Color.rgb(5,135,125), GRAY=Color.rgb(93,105,122);
    private LinearLayout root, content;
    private JSONArray items=new JSONArray(), suppliers=new JSONArray();
    private android.content.SharedPreferences prefs;
    private String tab="Home", caseName="My procurement inquiry", sourceText="";
    private int active=0, pdfPage=0;
    private PdfRenderer pdf;
    private StringBuilder pdfText;
    private ArrayList<GeometryBoqParser.Cell> pdfCells;
    private final String[] cities={"Lahore","Faisalabad","Gujranwala"};
    private final String[] catalog={"Household & Kitchen","Cleaning & Janitorial","Stationery & Paper","Electrical & Lighting","Textiles & Uniforms","Bedding & Mattresses","Packaging & Plastic","Home Bedding & Textiles","Hospital Bedding & Textiles","Hardware & Tools","Plumbing & Sanitary","Computers & IT","Printing & Toners","Office Furniture","Food & Refreshments","Sports & Recreation","Industrial Machinery","Other"};
    private final Set<String> selected=new LinkedHashSet<>();

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs=getSharedPreferences("procuremate_data_v1",MODE_PRIVATE);
        try{items=new JSONArray(prefs.getString("items","[]"));suppliers=new JSONArray(prefs.getString("suppliers","[]"));}catch(Exception ignored){}
        caseName=prefs.getString("caseName",caseName);
        String selectedCsv=prefs.getString("selected","Household & Kitchen,Cleaning & Janitorial,Stationery & Paper,Electrical & Lighting,Textiles & Uniforms,Bedding & Mattresses,Packaging & Plastic,Home Bedding & Textiles,Hospital Bedding & Textiles");
        for(String x:selectedCsv.split(","))if(!x.trim().isEmpty())selected.add(x.trim());
        render();
    }
    private void save(){prefs.edit().putString("items",items.toString()).putString("suppliers",suppliers.toString()).putString("caseName",caseName).putString("selected",android.text.TextUtils.join(",",selected)).apply();}
    private int dp(float n){return (int)(n*getResources().getDisplayMetrics().density+0.5f);}
    private JSONObject o(JSONArray a,int idx){return a.optJSONObject(idx);}
    private String s(JSONObject x,String key){return x==null?"":x.optString(key,"");}
    private TextView text(String value,int size,int color,boolean bold){
        TextView t=new TextView(this); t.setText(value); t.setTextColor(color); t.setTextSize(size);
        if(bold)t.setTypeface(null,1); t.setPadding(0,dp(4),0,dp(4)); return t;
    }
    private LinearLayout col(){LinearLayout l=new LinearLayout(this);l.setOrientation(1);return l;}
    private void gap(LinearLayout l,int h){View v=new View(this);l.addView(v,new LinearLayout.LayoutParams(1,dp(h)));}
    private GradientDrawable bg(int color,int radius){GradientDrawable g=new GradientDrawable();g.setColor(color);g.setCornerRadius(dp(radius));return g;}
    private LinearLayout card(){LinearLayout l=col();l.setPadding(dp(14),dp(12),dp(14),dp(14));l.setBackground(bg(Color.WHITE,14));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(0,0,0,dp(10)); content.addView(l,p);return l;}
    private Button btn(String label,Runnable job){
        Button b=new Button(this);b.setText(label);b.setTextSize(12);b.setAllCaps(false);
        b.setOnClickListener(v->job.run());return b;
    }
    private void addBtn(LinearLayout host,String label,Runnable job){host.addView(btn(label,job));}
    private LinearLayout actions(LinearLayout host){LinearLayout r=new LinearLayout(this);r.setOrientation(LinearLayout.HORIZONTAL);host.addView(r);return r;}
    private void action(LinearLayout row,String label,Runnable job){
        Button b=btn(label,job);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(45),1);
        p.setMargins(0,0,dp(3),0);row.addView(b,p);
    }
    private EditText field(String hint,String value){
        EditText e=new EditText(this);e.setSingleLine(false);e.setTextSize(15);e.setHint(hint);e.setText(value);
        e.setPadding(dp(8),dp(9),dp(8),dp(9));return e;
    }
    private void labeled(LinearLayout host,String label,EditText ed){host.addView(text(label,12,GRAY,true));host.addView(ed);}
    private void toast(String msg){Toast.makeText(this,msg,Toast.LENGTH_LONG).show();}
    private void render(){
        root=col();root.setBackgroundColor(Color.rgb(245,248,250));setContentView(root);
        LinearLayout header=col();header.setBackgroundColor(NAVY);header.setPadding(dp(18),dp(17),dp(18),dp(13));
        header.addView(text("ProcureMate Pakistan",23,Color.WHITE,true));
        header.addView(text("Tender-to-supplier assistant  •  Android beta",12,Color.rgb(199,222,233),false));
        header.addView(text("Made by Bilal",12,Color.rgb(199,222,233),true));
        root.addView(header);
        ScrollView scroll=new ScrollView(this);content=col();content.setPadding(dp(13),dp(15),dp(13),dp(8));
        scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        switch(tab){case "Items":showItems();break;case "Suppliers":showSuppliers();break;case "RFQ":showRFQ();break;case "Settings":showSettings();break;default:showHome();}
        LinearLayout nav=actions(root);nav.setBackgroundColor(Color.WHITE);
        for(String x:new String[]{"Home","Items","Suppliers","RFQ","Settings"}){
            Button b=btn(x,()->{tab=x;render();});b.setTextColor(x.equals(tab)?TEAL:NAVY);b.setPadding(0,0,0,0);
            nav.addView(b,new LinearLayout.LayoutParams(0,dp(55),1));
        }
    }
    private void showHome(){
        LinearLayout c=card();c.addView(text(caseName,20,NAVY,true));
        c.addView(text(items.length()+" BOQ items   ·   "+suppliers.length()+" supplier records",14,GRAY,false));
        LinearLayout a=actions(c);
        action(a,"Import file",this::pick);action(a,"Example tender",this::loadDemo);
        addBtn(c,"New inquiry / rename",this::newCase);
        c=card();c.addView(text("Supported imports",17,NAVY,true));
        c.addView(text("Images and screenshots • Scanned PDF (up to 20 pages) • TXT/CSV. OCR extraction requires review. For Excel BOQs, save a copy as CSV.",14,GRAY,false));
        c=card();c.addView(text("Your sourcing workflow",17,NAVY,true));
        c.addView(text("1. Import BOQ or add items\n2. Review names, specifications & quantities\n3. Search supplier leads in Lahore, Faisalabad, Gujranwala\n4. Save evidence and compare quoted prices\n5. Prepare editable RFQ and export CSV",14,NAVY,false));
        c=card();c.addView(text("Accuracy notice",16,NAVY,true));
        c.addView(text("Search results are unverified leads. Confirm company identity, specifications, phone numbers, stock, GST and delivery before quoting. No message is sent automatically.",13,GRAY,false));
    }
    private void newCase(){
        EditText name=field("New tender / inquiry name","");
        new AlertDialog.Builder(this).setTitle("Start fresh inquiry").setView(name)
          .setMessage("Starting a new inquiry clears locally saved items and supplier records. Export first if you need a backup.")
          .setNegativeButton("Cancel",null).setPositiveButton("Create",(d,w)->{
              items=new JSONArray();suppliers=new JSONArray();caseName=name.getText().toString().trim();
              if(caseName.isEmpty())caseName="My procurement inquiry";save();render();
          }).show();
    }
    private void loadDemo(){
        if(items.length()>0){toast("Demo adds example rows to the current inquiry.");}
        String[][] x={
            {"White paper ream","Legal size, 70 GSM, 500 sheets","3000","Ream","Stationery & Paper"},
            {"Towel","Large cotton, export quality","20","Nos","Home Bedding & Textiles"},
            {"Dust bin","Large size, best quality","5","Dozen","Cleaning & Janitorial"},
            {"Dettol surface cleaner","500ml or equivalent","5","Dozen","Cleaning & Janitorial"},
            {"Garden rubber pipe","1 inch, high quality","3000","Feet","Hardware & Tools"},
            {"Canon Pixma printer","G1010 ink tank","5","Nos","Computers & IT"},
            {"HP LaserJet printer","108A black-and-white","6","Nos","Computers & IT"},
            {"Air freshener","Best quality, different fragrances","5","Dozen","Household & Kitchen"},
            {"A4 size envelope","Packet of 50, fine quality","1000","Packet","Stationery & Paper"}
        };
        for(String[] row:x)addItem(row[0],row[1],row[2],row[3],row[4],"SAMPLE - user reference screenshots");
        save();tab="Items";render();
    }
    private void addItem(String name,String spec,String qty,String unit,String category,String source){
        JSONObject j=new JSONObject();
        try{j.put("name",name);j.put("spec",spec);j.put("qty",qty);j.put("unit",unit);j.put("category",category);j.put("source",source);items.put(j);}catch(Exception ignored){}
    }
    private void showItems(){
        LinearLayout heading=card();heading.addView(text("BOQ items ("+items.length()+")",19,NAVY,true));
        LinearLayout a=actions(heading);action(a,"Import",this::pick);action(a,"+ Add item",()->editItem(-1));
        action(a,"Export CSV",this::createExport);
        if(items.length()==0){LinearLayout c=card();c.addView(text("No items yet. Import a tender screenshot/PDF or tap Example tender to test.",14,GRAY,false));}
        for(int i=0;i<items.length();i++){
            final int idx=i;JSONObject j=o(items,i);if(j==null)continue;
            LinearLayout c=card();c.addView(text((i+1)+". "+s(j,"name"),17,NAVY,true));
            c.addView(text(s(j,"qty")+" "+s(j,"unit")+"   ·   "+s(j,"category"),13,TEAL,true));
            c.addView(text(s(j,"spec"),13,GRAY,false));
            if(j.optBoolean("review",false))c.addView(text("Needs review: verify this row, quantity and unit against the tender",12,Color.rgb(165,87,19),true));
            if(!s(j,"source").isEmpty())c.addView(text("Source: "+s(j,"source"),11,GRAY,false));
            LinearLayout row=actions(c);
            action(row,"Edit",()->editItem(idx));
            action(row,"Find",()->searchItem(idx));
            action(row,"RFQ",()->{active=idx;tab="RFQ";render();});
            action(row,"Delete",()->new AlertDialog.Builder(this).setTitle("Delete item?")
                .setPositiveButton("Delete",(d,w)->{items.remove(idx);save();render();}).setNegativeButton("Cancel",null).show());
        }
    }
    private void editItem(int index){
        JSONObject old=index<0?null:o(items,index);
        LinearLayout box=col();box.setPadding(dp(17),dp(8),dp(17),0);
        EditText name=field("Product name",s(old,"name")), spec=field("Tender specifications",s(old,"spec")),
                qty=field("Quantity",s(old,"qty")),unit=field("Unit (Nos/Box/Dozen/Feet etc.)",s(old,"unit")),
                category=field("Category",s(old,"category").isEmpty()?"Other":s(old,"category"));
        labeled(box,"Product",name);labeled(box,"Specifications / brand or equivalent",spec);
        labeled(box,"Quantity",qty);labeled(box,"Original tender unit",unit);labeled(box,"Category (editable)",category);
        ScrollView sc=new ScrollView(this);sc.addView(box);
        new AlertDialog.Builder(this).setTitle(index<0?"Add BOQ item":"Edit BOQ item").setView(sc)
          .setNegativeButton("Cancel",null).setPositiveButton("Save",(d,w)->{
            if(name.getText().toString().trim().isEmpty()){toast("Product name is required");return;}
            JSONObject j=old==null?new JSONObject():old;
            try{j.put("name",name.getText().toString().trim());j.put("spec",spec.getText().toString().trim());
                j.put("qty",qty.getText().toString().trim());j.put("unit",unit.getText().toString().trim());
                j.put("category",category.getText().toString().trim());
                j.put("review",qty.getText().toString().trim().isEmpty()||unit.getText().toString().trim().isEmpty());
                if(old==null)j.put("source","Manual entry");
                if(index<0)items.put(j);}catch(Exception ignored){}
            save();render();
          }).show();
    }
    private void searchItem(int idx){
        JSONObject item=o(items,idx);if(item==null)return;active=idx;
        String[] choices={"Search web (no key needed)","Auto-find web leads (Serper key needed)","Manually add supplier"};
        new AlertDialog.Builder(this).setTitle("Source: "+s(item,"name"))
          .setItems(choices,(d,choice)->{
            if(choice==0){
                String q=s(item,"name")+" "+s(item,"spec")+" wholesale manufacturer distributor supplier Lahore Faisalabad Gujranwala Pakistan";
                openLink("https://www.google.com/search?q="+Uri.encode(q));
            }else if(choice==1)autoSearch(idx);else editSupplier(-1,idx,null);
          }).show();
    }
    private void openLink(String url){try{startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url)));}catch(Exception e){toast("Cannot open URL: "+e.getMessage());}}
    private void autoSearch(int idx){
        final String key=prefs.getString("serperKey","").trim();
        if(key.isEmpty()){new AlertDialog.Builder(this).setMessage("To automatically discover supplier leads, add a Serper Search API key under Settings. Without a key, use Search web for free.").setPositiveButton("Settings",(d,w)->{tab="Settings";render();}).setNegativeButton("Cancel",null).show();return;}
        JSONObject item=o(items,idx);if(item==null)return;
        toast("Searching three priority cities…");
        new Thread(()->{
            JSONArray all=new JSONArray();String error="";
            for(String city:cities){
                try{
                    URL endpoint=new URL("https://google.serper.dev/search");
                    HttpURLConnection conn=(HttpURLConnection)endpoint.openConnection();conn.setConnectTimeout(12000);conn.setReadTimeout(18000);
                    conn.setRequestMethod("POST");conn.setDoOutput(true);conn.setRequestProperty("X-API-KEY",key);conn.setRequestProperty("Content-Type","application/json");
                    JSONObject request=new JSONObject();request.put("q",s(item,"name")+" "+s(item,"spec")+" wholesaler manufacturer distributor "+city+" Pakistan");
                    request.put("gl","pk");request.put("num",6);
                    try(OutputStream out=conn.getOutputStream()){out.write(request.toString().getBytes(StandardCharsets.UTF_8));}
                    int status=conn.getResponseCode();
                    if(status!=200){error="Search API HTTP "+status;conn.disconnect();break;}
                    String json=read(conn.getInputStream(),800000);
                    JSONArray organic=new JSONObject(json).optJSONArray("organic");
                    if(organic!=null)for(int k=0;k<organic.length();k++){
                        JSONObject lead=organic.optJSONObject(k);if(lead==null)continue;
                        JSONObject copy=new JSONObject();copy.put("name",lead.optString("title"));copy.put("url",lead.optString("link"));
                        copy.put("notes",lead.optString("snippet"));copy.put("city",city);all.put(copy);
                    }conn.disconnect();
                }catch(Exception ex){error=ex.getMessage();break;}
            }
            String msg=error;runOnUiThread(()->{
                if(!msg.isEmpty())toast("Supplier search: "+msg);
                if(all.length()==0){toast("No leads returned; try free web search");return;}
                showLeads(idx,all);
            });
        }).start();
    }
    private void showLeads(int idx,JSONArray leads){
        final ArrayList<String> options=new ArrayList<>();
        final ArrayList<JSONObject> list=new ArrayList<>();
        Set<String> unique=new HashSet<>();
        for(int i=0;i<leads.length();i++){
            JSONObject j=o(leads,i);if(j==null||s(j,"url").isEmpty()||!unique.add(s(j,"url")))continue;
            list.add(j);options.add(s(j,"city")+": "+s(j,"name"));
        }
        new AlertDialog.Builder(this).setTitle("Unverified web leads ("+list.size()+")")
            .setMessage("These are web search results, NOT verified manufacturers or confirmed contact numbers. Tap one to review its source or save it.")
            .setItems(options.toArray(new String[0]),(d,w)->{
                JSONObject lead=list.get(w);String[] actions={"Open original source","Save lead to supplier directory"};
                new AlertDialog.Builder(this).setTitle(s(lead,"name")).setMessage(s(lead,"notes"))
                  .setItems(actions,(dlg,n)->{
                    if(n==0)openLink(s(lead,"url"));else editSupplier(-1,idx,lead);
                  }).show();
            }).setPositiveButton("Done",null).show();
    }
    private void showSuppliers(){
        LinearLayout heading=card();heading.addView(text("Supplier directory ("+suppliers.length()+")",19,NAVY,true));
        heading.addView(text("Contacts and prices are your records; always verify before bidding.",12,GRAY,false));
        addBtn(heading,"+ Add supplier / quotation",()->editSupplier(-1,items.length()==0?-1:Math.min(active,items.length()-1),null));
        for(int i=0;i<suppliers.length();i++){
            int idx=i;JSONObject j=o(suppliers,i);if(j==null)continue;
            LinearLayout c=card();c.addView(text(s(j,"name"),17,NAVY,true));
            c.addView(text(s(j,"city")+"  ·  "+s(j,"type")+"  ·  "+s(j,"status"),12,TEAL,true));
            if(!s(j,"phone").isEmpty())c.addView(text("Contact: "+s(j,"phone"),13,GRAY,false));
            if(!s(j,"price").isEmpty())c.addView(text("Quoted unit price: PKR "+s(j,"price")+"  (confirm tax & delivery)",13,NAVY,false));
            c.addView(text("For: "+s(j,"item"),12,GRAY,false));
            LinearLayout a=actions(c);action(a,"Edit",()->editSupplier(idx,-1,null));
            action(a,"Source",()->{if(!s(j,"url").isEmpty())openLink(s(j,"url"));else toast("No source URL saved");});
            action(a,"Delete",()->new AlertDialog.Builder(this).setMessage("Remove supplier record?")
                .setPositiveButton("Remove",(d,w)->{suppliers.remove(idx);save();render();}).setNegativeButton("Cancel",null).show());
        }
    }
    private void editSupplier(int index,int itemIdx,JSONObject suggestion){
        JSONObject old=index<0?null:o(suppliers,index);
        LinearLayout box=col();box.setPadding(dp(16),dp(5),dp(16),0);
        String itemName=s(old,"item");
        if(itemName.isEmpty()&&itemIdx>=0)itemName=s(o(items,itemIdx),"name");
        EditText item=field("Item being sourced",itemName),
                name=field("Company / supplier name",old!=null?s(old,"name"):s(suggestion,"name")),
                city=field("City",old!=null?s(old,"city"):s(suggestion,"city")),
                type=field("Type (manufacturer / distributor / unknown)",s(old,"type")),
                phone=field("Public contact number",s(old,"phone")),
                url=field("Evidence / official website URL",old!=null?s(old,"url"):s(suggestion,"url")),
                price=field("Quoted unit price PKR (blank if not confirmed)",s(old,"price")),
                notes=field("MOQ, lead time, freight, verification notes",old!=null?s(old,"notes"):s(suggestion,"notes")),
                status=field("Status (Unverified / Contact confirmed / Quote received)",old==null?"Unverified":s(old,"status"));
        labeled(box,"Associated BOQ item",item);labeled(box,"Supplier",name);labeled(box,"City",city);
        labeled(box,"Business type (do not assume)",type);labeled(box,"Phone / WhatsApp",phone);
        labeled(box,"Evidence/source URL",url);labeled(box,"Actual quoted price only",price);
        labeled(box,"Verification",status);labeled(box,"Notes",notes);
        ScrollView sc=new ScrollView(this);sc.addView(box);
        new AlertDialog.Builder(this).setTitle(index<0?"Add supplier":"Edit supplier").setView(sc)
          .setNegativeButton("Cancel",null).setPositiveButton("Save",(d,w)->{
            if(name.getText().toString().trim().isEmpty()){toast("Supplier name required");return;}
            JSONObject j=old==null?new JSONObject():old;
            try{
                j.put("item",item.getText());j.put("name",name.getText());j.put("city",city.getText());j.put("type",type.getText());
                j.put("phone",phone.getText());j.put("url",url.getText());j.put("price",price.getText());
                j.put("notes",notes.getText());j.put("status",status.getText());
                if(old==null)suppliers.put(j);
            }catch(Exception ignored){}
            save();render();
          }).show();
    }
    private void showRFQ(){
        LinearLayout c=card();c.addView(text("Editable supplier inquiry",19,NAVY,true));
        if(items.length()==0){c.addView(text("Add BOQ items to draft an inquiry.",14,GRAY,false));return;}
        if(active>=items.length())active=0;
        Spinner spin=new Spinner(this);ArrayList<String> labels=new ArrayList<>();
        for(int i=0;i<items.length();i++)labels.add((i+1)+". "+s(o(items,i),"name"));
        ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels);
        spin.setAdapter(adapter);spin.setSelection(active);c.addView(spin);
        final EditText rfq=field("Draft",buildRFQ(active,false));
        rfq.setMinLines(10);rfq.setGravity(Gravity.TOP);c.addView(rfq);
        spin.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(android.widget.AdapterView<?> p){}
            public void onItemSelected(android.widget.AdapterView<?> p,View v,int position,long id){active=position;rfq.setText(buildRFQ(position,false));}
        });
        LinearLayout a=actions(c);action(a,"English",()->rfq.setText(buildRFQ(active,false)));
        action(a,"اردو",()->rfq.setText(buildRFQ(active,true)));
        action(a,"All items",()->rfq.setText(buildAllRFQ()));
        a=actions(c);action(a,"Copy",()->{
            ((android.content.ClipboardManager)getSystemService(CLIPBOARD_SERVICE))
             .setPrimaryClip(ClipData.newPlainText("Supplier RFQ",rfq.getText().toString()));toast("Copied to clipboard");
        });
        action(a,"WhatsApp / Share",()->{
            Intent share=new Intent(Intent.ACTION_SEND);share.setType("text/plain");
            share.putExtra(Intent.EXTRA_TEXT,rfq.getText().toString());startActivity(Intent.createChooser(share,"Share inquiry draft"));
        });
        c=card();c.addView(text("You approve every inquiry",15,NAVY,true));
        c.addView(text("Drafts are never sent automatically. Edit prices, branding, delivery requirements, sample and tax terms before sharing.",12,GRAY,false));
    }
    private String buildRFQ(int idx,boolean urdu){
        JSONObject j=o(items,idx);if(j==null)return "";
        if(urdu)return "السلام علیکم،\nبراہ کرم درج ذیل آئٹم کے لیے اپنی بہترین ہول سیل کوٹیشن فراہم کریں:\n\nآئٹم: "+s(j,"name")+
            "\nتفصیل: "+s(j,"spec")+"\nتعداد: "+s(j,"qty")+" "+s(j,"unit")+
            "\n\nبراہ کرم فی یونٹ قیمت، جی ایس ٹی، کم از کم آرڈر، دستیابی، ڈلیوری چارجز، وقت اور وارنٹی واضح کریں۔\nشکریہ";
        return "Assalam-o-Alaikum,\nPlease share your best wholesale quotation for the following:\n\nItem: "+s(j,"name")+
            "\nSpecification: "+s(j,"spec")+"\nQuantity: "+s(j,"qty")+" "+s(j,"unit")+
            "\n\nPlease confirm exact specification/brand or equivalent, unit price in PKR, GST, MOQ, stock, delivery charges to destination, lead time, payment terms, warranty, and quotation validity.\n\nThank you.";
    }
    private String buildAllRFQ(){
        StringBuilder b=new StringBuilder("Assalam-o-Alaikum,\nPlease quote the following items (all specifications must be met):\n");
        for(int i=0;i<items.length();i++){JSONObject j=o(items,i);b.append("\n").append(i+1).append(". ").append(s(j,"name")).append(" — ")
            .append(s(j,"qty")).append(" ").append(s(j,"unit")).append("; ").append(s(j,"spec"));}
        b.append("\n\nPlease provide item-wise PKR unit price, GST, freight, availability, delivery lead time and quote validity. Thank you.");
        return b.toString();
    }
    private void showSettings(){
        LinearLayout c=card();c.addView(text("Product categories",19,NAVY,true));
        c.addView(text("Multiple categories can be active. Item classification is always editable.",12,GRAY,false));
        for(String name:catalog){
            CheckBox cb=new CheckBox(this);cb.setText(name);cb.setTextSize(13);cb.setChecked(selected.contains(name));
            cb.setOnCheckedChangeListener((button,checked)->{if(checked)selected.add(name);else selected.remove(name);save();});c.addView(cb);
        }
        addBtn(c,"Add custom category",()->{
            EditText ed=field("Category name","");
            new AlertDialog.Builder(this).setTitle("Custom category").setView(ed).setPositiveButton("Add",(d,w)->{
                String v=ed.getText().toString().trim();if(!v.isEmpty()){selected.add(v);save();render();}
            }).setNegativeButton("Cancel",null).show();
        });
        c=card();c.addView(text("Optional automated web search",18,NAVY,true));
        c.addView(text("For automatic discovery of web leads, enter your own Serper Search API key. Without a key you can still search the browser at no charge. Results are not verified contacts.",12,GRAY,false));
        EditText api=field("Serper API key",prefs.getString("serperKey",""));api.setSingleLine(true);
        api.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);c.addView(api);
        addBtn(c,"Save API key",()->{prefs.edit().putString("serperKey",api.getText().toString().trim()).apply();toast("Search preference saved");});
        c=card();c.addView(text("Privacy and limitations",17,NAVY,true));
        c.addView(text("BOQs and contacts are saved on this device. Live searches transmit the search item names to the selected web provider; imported PDFs/images are not uploaded by this app. No multi-device team sync yet. Urdu-script OCR and Excel XLSX need a later release.",13,GRAY,false));
        addBtn(c,"Export item schedule to CSV",this::createExport);
        c=card();c.addView(text("About ProcureMate",17,NAVY,true));
        c.addView(text("Owner / Developer: Bilal\nVersion: 0.1.1-beta",14,GRAY,false));
    }
    private void pick(){
        Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("*/*");
        i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,true);
        i.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/*","application/pdf","text/plain","text/csv","application/csv"});
        startActivityForResult(i,101);
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);if(result!=RESULT_OK||data==null)return;
        if(request==101){
            if(data.getClipData()!=null){ClipData clips=data.getClipData();for(int i=0;i<clips.getItemCount();i++)importUri(clips.getItemAt(i).getUri());}
            else if(data.getData()!=null)importUri(data.getData());
        }else if(request==200 && data.getData()!=null){
            try(OutputStream out=getContentResolver().openOutputStream(data.getData())){
                out.write(createCsv().getBytes(StandardCharsets.UTF_8));toast("CSV exported");
            }catch(Exception e){toast("Export failed: "+e.getMessage());}
        }
    }
    private String fileName(Uri uri){
        try(Cursor c=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null)){
            if(c!=null&&c.moveToFirst())return c.getString(0);
        }catch(Exception ignored){}return "Imported file";
    }
    private void importUri(Uri uri){
        String mime=getContentResolver().getType(uri);String filename=fileName(uri);
        if("application/pdf".equals(mime)||filename.toLowerCase(Locale.US).endsWith(".pdf")){
            try{ParcelFileDescriptor pfd=getContentResolver().openFileDescriptor(uri,"r");
                if(pfd==null)throw new IOException("Cannot open PDF");
                pdf=new PdfRenderer(pfd);pdfPage=0;pdfText=new StringBuilder();pdfCells=new ArrayList<>();processPdf(filename);
            }catch(Exception e){toast("PDF read error: "+e.getMessage());}
        }else if((mime!=null&&mime.startsWith("image/"))||filename.matches("(?i).*\\.(png|jpg|jpeg|webp)$")){
            try(InputStream in=getContentResolver().openInputStream(uri)){
                Bitmap bitmap=BitmapFactory.decodeStream(in);if(bitmap==null)throw new IOException("Invalid image");
                ocrLayout(bitmap,1,(txt,cells)->reviewParsed(GeometryBoqParser.parse(cells),txt,filename),()->toast("OCR failed for "+filename));
            }catch(Exception e){toast("Image read error: "+e.getMessage());}
        }else if(filename.toLowerCase(Locale.US).endsWith(".xlsx")){
            toast("Save Excel as CSV first; XLSX support comes in a later version.");
        }else{
            try(InputStream in=getContentResolver().openInputStream(uri)){reviewText(read(in,3000000),filename);}
            catch(Exception e){toast("Text import failed: "+e.getMessage());}
        }
    }

    private interface OnLayout { void done(String text,ArrayList<GeometryBoqParser.Cell> cells); }
    private void ocrLayout(Bitmap bitmap,int page,OnLayout cb,Runnable failure){
        TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS).process(InputImage.fromBitmap(bitmap,0))
           .addOnSuccessListener(result->{
               ArrayList<GeometryBoqParser.Cell> cells=new ArrayList<>();
               for(com.google.mlkit.vision.text.Text.TextBlock block:result.getTextBlocks()){
                   for(com.google.mlkit.vision.text.Text.Line line:block.getLines()){
                       Rect r=line.getBoundingBox();
                       if(r!=null)cells.add(new GeometryBoqParser.Cell(line.getText(),r.left,r.top,r.right,r.bottom,page));
                   }
               }
               String raw=result.getText();bitmap.recycle();cb.done(raw,cells);
           })
           .addOnFailureListener(e->{bitmap.recycle();failure.run();});
    }
    private void processPdf(String filename){
        if(pdf==null)return;
        if(pdfPage>=Math.min(pdf.getPageCount(),20)){
            pdf.close();pdf=null;
            reviewParsed(GeometryBoqParser.parse(pdfCells),pdfText.toString(),filename);
            return;
        }
        PdfRenderer.Page page=pdf.openPage(pdfPage);
        float factor=Math.min(2.0f,1600f/Math.max(page.getWidth(),page.getHeight()));
        int w=Math.max(1,(int)(page.getWidth()*factor)),h=Math.max(1,(int)(page.getHeight()*factor));
        Bitmap bm=Bitmap.createBitmap(w,h,Bitmap.Config.ARGB_8888);bm.eraseColor(Color.WHITE);
        page.render(bm,null,null,PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);page.close();
        final int number=++pdfPage;
        ocrLayout(bm,number,(raw,cells)->{
              pdfCells.addAll(cells);
              pdfText.append("\n--- PAGE ").append(number).append(" ---\n").append(raw);
              processPdf(filename);
           },()->{pdfText.append("\n--- PAGE ").append(number).append(" OCR ERROR ---");processPdf(filename);});
    }
    private void reviewParsed(java.util.List<GeometryBoqParser.Item> extracted,String raw,String source){
        if(extracted==null||extracted.isEmpty()){
            reviewText(raw,source);return;
        }
        final java.util.List<GeometryBoqParser.Item> rows=GeometryBoqParser.deduplicate(extracted);
        int uncertain=0;for(GeometryBoqParser.Item item:rows)if(item.needsReview)uncertain++;
        LinearLayout list=col();list.setPadding(dp(14),dp(8),dp(14),dp(8));
        list.addView(text("Review "+rows.size()+" separate items. "+uncertain+" have missing or uncertain quantity/unit. Verify against the original document after importing.",13,GRAY,false));
        for(GeometryBoqParser.Item r:rows){
            String number=r.serial.isEmpty()?"":r.serial+". ";
            list.addView(text(number+r.name,14,NAVY,true));
            list.addView(text("Qty: "+(r.qty.isEmpty()?"CHECK":r.qty)+"  Unit: "+(r.unit.isEmpty()?"CHECK":r.unit)+"  Page: "+r.page,12,r.needsReview?Color.rgb(165,87,19):TEAL,false));
        }
        ScrollView scroll=new ScrollView(this);scroll.addView(list);
        new AlertDialog.Builder(this).setTitle("Review BOQ: "+source).setView(scroll)
            .setNegativeButton("Cancel",null)
            .setNeutralButton("Review raw text",(d,w)->reviewText(raw,source))
            .setPositiveButton("Import "+rows.size()+" items",(d,w)->{
                int added=importParsed(rows,source);save();tab="Items";render();
                toast(added+" structured BOQ rows imported. Verify highlighted fields before quotation.");
            }).show();
    }
    private int importParsed(java.util.List<GeometryBoqParser.Item> rows,String source){
        Set<String> seen=new HashSet<>();
        for(int i=0;i<items.length();i++){
            JSONObject j=o(items,i);
            seen.add((s(j,"serial")+"|"+s(j,"name")+"|"+s(j,"qty")+"|"+s(j,"unit")).toLowerCase(Locale.ROOT));
        }
        int added=0;
        for(GeometryBoqParser.Item row:rows){
            String key=(row.serial+"|"+row.name+"|"+row.qty+"|"+row.unit).toLowerCase(Locale.ROOT);
            if(!seen.add(key))continue;
            String label=source+" (page "+row.page+", row "+row.row+")";
            addItem(row.name,row.spec,row.qty,row.unit,categorize(row.name),label);
            try{
                JSONObject j=o(items,items.length()-1);
                j.put("serial",row.serial);
                j.put("review",row.needsReview);
                j.put("sourcePage",row.page);
                j.put("sourceRow",row.row);
            }catch(Exception ignored){}
            added++;
        }
        return added;
    }
    private String read(InputStream in,int max) throws IOException {
        ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buf=new byte[8192];int n,remaining=max;
        while(remaining>0&&(n=in.read(buf,0,Math.min(buf.length,remaining)))!=-1){out.write(buf,0,n);remaining-=n;}
        return out.toString("UTF-8");
    }
    private void reviewText(String extracted,String source){
        if(extracted==null||extracted.trim().isEmpty()){toast("No text found. Try a clearer scan or add items manually.");return;}
        sourceText=extracted;
        EditText ed=field("OCR output: correct any mistakes before parsing",extracted);ed.setGravity(Gravity.TOP);
        ScrollView wrap=new ScrollView(this);wrap.setPadding(dp(15),dp(10),dp(15),0);wrap.addView(ed);
        new AlertDialog.Builder(this).setTitle("Review text: "+source)
         .setMessage("OCR is imperfect on scanned tables. Check quantities, units and each product after parsing.")
         .setView(wrap).setNegativeButton("Cancel",null).setPositiveButton("Extract rows",(d,w)->{
             int added=extract(ed.getText().toString(),source);save();tab="Items";render();
             toast(added+" possible item rows extracted. Review/edit all tender specifications.");
         }).show();
    }
    private int extract(String text,String source){
        int added=0;
        Pattern row=Pattern.compile("(?i)^\\s*(?:\\d{1,3}\\s*[.)]?\\s+)?(.{4,120}?)\\s+(\\d+(?:\\.\\d+)?)\\s*(Nos?|P/No|Each|Pcs?|Pieces?|Packets?|Packs?|Box(?:es)?|Dozen|Bottles?|Liters?|Litres?|P-Lit|Feet|Ft|Kg|P-Kg|Reams?|Rolls?)\\s*$");
        Set<String> fingerprints=new HashSet<>();
        for(int i=0;i<items.length();i++){JSONObject j=o(items,i);fingerprints.add((s(j,"name")+"|"+s(j,"qty")+"|"+s(j,"unit")).toLowerCase(Locale.US));}
        for(String line:text.split("\\r?\\n")){
            line=line.replaceAll("\\s+"," ").trim();if(line.length()>180)continue;
            Matcher m=row.matcher(line);if(!m.find())continue;
            String name=m.group(1).replaceAll("^\\d{1,3}\\s*[.)]?\\s*","").trim();
            if(name.length()<4||name.toLowerCase(Locale.US).startsWith("estimated"))continue;
            String qty=m.group(2),unit=m.group(3);
            String fp=(name+"|"+qty+"|"+unit).toLowerCase(Locale.US);
            if(!fingerprints.add(fp))continue;
            addItem(name,"CHECK AGAINST ORIGINAL TENDER — OCR row",qty,unit,categorize(name),source);added++;
        }return added;
    }
    private String categorize(String name){
        String x=name.toLowerCase(Locale.US);
        if(x.matches(".*(paper|pen|notebook|envelop|stapl|marker|eraser|highlighter|tape|stationer).*"))return "Stationery & Paper";
        if(x.matches(".*(towel|sheet|blanket|pillow|curtain|mattress|linen|fabric).*"))return "Home Bedding & Textiles";
        if(x.matches(".*(toilet|detto|harpic|brush|broom|mop|dustbin|soap|wash|cleaner|disinfectant).*"))return "Cleaning & Janitorial";
        if(x.matches(".*(cable|printer|network|internet hub|cat 6|laserjet|pixma).*"))return "Computers & IT";
        if(x.matches(".*(pipe|spanner|wrench|shovel|ladder|lock|plier|screwdriver|bamboo).*"))return "Hardware & Tools";
        if(x.matches(".*(bulb|light|wire|electri|socket|extension).*"))return "Electrical & Lighting";
        return "Household & Kitchen";
    }
    private String csv(String in){return "\""+(in==null?"":in).replace("\"","\"\"")+"\"";}
    private String createCsv(){
        StringBuilder b=new StringBuilder("\uFEFFNo,Product,Specification,Quantity,Unit,Category,Source\n");
        for(int i=0;i<items.length();i++){JSONObject j=o(items,i);
            b.append(i+1);
            for(String key:new String[]{"name","spec","qty","unit","category","source"})b.append(",").append(csv(s(j,key)));
            b.append("\r\n");
        }
        b.append("\r\nSupplier,Associated item,City,Type,Contact,Source URL,Status,Quoted unit price PKR,Notes\n");
        for(int i=0;i<suppliers.length();i++){JSONObject j=o(suppliers,i);
            for(String key:new String[]{"name","item","city","type","phone","url","status","price","notes"}){
                if(!key.equals("name"))b.append(",");b.append(csv(s(j,key)));
            }b.append("\r\n");
        }return b.toString();
    }
    private void createExport(){
        Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("text/csv");
        i.putExtra(Intent.EXTRA_TITLE,"procuremate-items-and-suppliers.csv");startActivityForResult(i,200);
    }
}
