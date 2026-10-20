package pk.procuremate.app;

import java.util.*;
import java.util.regex.*;

/** Table-aware, pure-Java parser. Position is preserved from OCR, including page number. */
public final class GeometryBoqParser {
    private GeometryBoqParser() {}
    public static final class Cell {
        public final String text;
        public final int left,top,right,bottom,page;
        public Cell(String text,int left,int top,int right,int bottom,int page){
            this.text=text==null?"":text.trim();this.left=left;this.top=top;
            this.right=right;this.bottom=bottom;this.page=page;
        }
        int cy(){return (top+bottom)/2;}
        int h(){return Math.max(1,bottom-top);}
    }
    public static final class Item {
        public String serial="",name="",spec="",qty="",unit="";
        public int page,row;
        public boolean needsReview=true;
    }
    private static final Pattern SERIAL=Pattern.compile("^(\\d{1,4})\\s*[.)-]?$");
    private static final Pattern NUMBERED=Pattern.compile("^(\\d{1,4})\\s*[.)-]\\s*(\\S.*)$");
    private static final Pattern QTYUNIT=Pattern.compile("(?i)^(.+?)\\s+(\\d+(?:[.,]\\d+)?)\\s+(nos?|pcs?|pieces?|each|boxes?|packets?|packs?|dozens?|dz|bottles?|liters?|litres?|ltr|kg|grams?|reams?|rolls?|feet|ft|meters?|pairs?|sets?)\\s*$");
    private static final Pattern UNIT=Pattern.compile("(?i)^(nos?|pcs?|pieces?|each|boxes?|packets?|packs?|dozens?|dz|bottles?|liters?|litres?|ltr|kg|grams?|reams?|rolls?|feet|ft|meters?|pairs?|sets?)\\.?$");
    private static final Pattern QTY=Pattern.compile("^\\d{1,7}(?:[.,]\\d{1,3})?$");
    private static final Pattern HEADER=Pattern.compile("(?i)^(sr\\.?\\s*no\\.?|s\\.?\\s*no\\.?|serial\\s*no\\.?|no\\.?|article\\s*name|item\\s*name|description|particulars|name\\s*of\\s*(?:the\\s*)?(?:article|item)|quantity|qty\\.?|unit|uom|unit\\s*of\\s*measure|rate|amount)$");
    private static final Pattern IGNORE=Pattern.compile("(?i)^(page\\s*\\d+|grand\\s*total|subtotal|total|estimated\\s*(?:cost|budget)|budget|signature|date|gst\\b.*|tax\\b.*|sr\\s*no|article\\s*name|item\\s*name|qty|unit)$");
    private static final class Band {
        final ArrayList<Cell> cells=new ArrayList<>();
        int y, h;
        Band(Cell c){cells.add(c);y=c.cy();h=c.h();}
        void add(Cell c){cells.add(c);y=(y*(cells.size()-1)+c.cy())/cells.size();h=Math.min(h,c.h());}
    }
    public static List<Item> parse(List<Cell> input){
        if(input==null||input.isEmpty())return Collections.emptyList();
        TreeMap<Integer,List<Cell>> byPage=new TreeMap<>();
        for(Cell c:input)if(!c.text.isEmpty())byPage.computeIfAbsent(c.page,k->new ArrayList<>()).add(c);
        ArrayList<Item> out=new ArrayList<>();
        for(Map.Entry<Integer,List<Cell>> page:byPage.entrySet()){
            List<Cell> cells=page.getValue();
            cells.sort(Comparator.comparingInt(Cell::cy).thenComparingInt(c->c.left));
            ArrayList<Band> bands=new ArrayList<>();
            for(Cell c:cells){
                Band best=null;int distance=Integer.MAX_VALUE;
                for(int k=bands.size()-1;k>=0;k--){
                    Band b=bands.get(k);int gap=Math.abs(b.y-c.cy());
                    int maxGap=Math.max(3,Math.min(b.h,c.h())*55/100);
                    if(gap<distance&&gap<=maxGap){best=b;distance=gap;}
                    if(b.y < c.cy()-Math.max(15,c.h()*2))break;
                }
                if(best==null)bands.add(new Band(c));else best.add(c);
            }
            for(Band b:bands)b.cells.sort(Comparator.comparingInt(c->c.left));
            int articleX=-1, qtyX=Integer.MAX_VALUE, unitX=Integer.MAX_VALUE, headerY=Integer.MIN_VALUE;
            for(Band b:bands)for(Cell c:b.cells){
                String h=c.text.toLowerCase(Locale.ROOT).replaceAll("[^a-z ]","").replaceAll(" +"," ").trim();
                if(h.equals("article name")||h.equals("item name")||h.equals("description")||h.equals("particulars")||h.equals("name of item")){
                    articleX=c.left;headerY=Math.max(headerY,b.y);
                }
                if(h.equals("qty")||h.equals("quantity"))qtyX=Math.min(qtyX,c.left);
                if(h.equals("unit")||h.equals("uom")||h.equals("unit of measure"))unitX=Math.min(unitX,c.left);
            }
            Item current=null;int previousY=-1, previousH=12;
            for(Band b:bands){
                if(headerY!=Integer.MIN_VALUE&&b.y<=headerY)continue;
                Item item=parseBand(b.cells,articleX,qtyX,unitX);
                if(item==null)continue;
                item.page=page.getKey();
                if(item.name.isEmpty())continue;
                if(HEADER.matcher(item.name).matches()||IGNORE.matcher(item.name).matches())continue;
                if(item.name.length()<3||item.name.matches("[\\d.,%/ ]+"))continue;
                if(current!=null && item.serial.isEmpty() && item.qty.isEmpty() && item.unit.isEmpty() &&
                   !current.name.isEmpty() && b.y-previousY<=Math.max(previousH*2,25) &&
                   (item.name.startsWith("(")||item.name.startsWith("-")||item.name.toLowerCase(Locale.ROOT).matches("^(?:or equivalent|equivalent|size|quality|brand|gsm|specification|packing|colour|color)\\b.*"))){
                    current.spec=(current.spec.isEmpty()?"":current.spec+" ")+item.name;
                }else{
                    // Always keep item-like text with missing quantity for review; never invent quantities.
                    item.row=out.size()+1;out.add(item);current=item;
                }
                previousY=b.y;previousH=b.h;
            }
        }
        return out;
    }
    private static Item parseBand(List<Cell> cells,int articleX,int qtyX,int unitX){
        Item item=new Item();StringBuilder words=new StringBuilder();
        for(Cell c:cells){
            String s=c.text.trim();
            if(s.isEmpty()||HEADER.matcher(s).matches())continue;
            Matcher serial=SERIAL.matcher(s), numbered=NUMBERED.matcher(s);
            boolean beforeArticle=articleX<0 || c.left<articleX;
            if(serial.matches()&&beforeArticle&&item.serial.isEmpty()){
                item.serial=serial.group(1);continue;
            }
            if(numbered.matches()&&item.serial.isEmpty()){
                item.serial=numbered.group(1);s=numbered.group(2);
            }
            // Column position has priority over ambiguous text (e.g. 'Dettol 500ml').
            if(qtyX<Integer.MAX_VALUE&&c.left>=qtyX-4 && (unitX==Integer.MAX_VALUE||c.left<unitX-4)&&QTY.matcher(s).matches()){
                item.qty=s;continue;
            }
            if(unitX<Integer.MAX_VALUE&&c.left>=unitX-4&&UNIT.matcher(s).matches()){
                item.unit=s;continue;
            }
            if(words.length()>0)words.append(' ');
            words.append(s);
        }
        String name=words.toString().trim();
        Matcher m=QTYUNIT.matcher(name);
        if(m.matches() && item.qty.isEmpty()&&item.unit.isEmpty()){
            name=m.group(1).trim();item.qty=m.group(2);item.unit=m.group(3);
        }
        // If quantity and unit occur in their own right-hand cells without usable headers,
        // only use the last two independent cells; never treat '500ml' as demand quantity.
        if(item.qty.isEmpty()&&cells.size()>=3){
            Cell last=cells.get(cells.size()-1),prev=cells.get(cells.size()-2);
            if(UNIT.matcher(last.text).matches()&&QTY.matcher(prev.text).matches()&&prev.left>cells.get(0).left+15){
                item.qty=prev.text;item.unit=last.text;
                name=name.replaceFirst("\\s+"+Pattern.quote(prev.text)+"\\s+"+Pattern.quote(last.text)+"$","").trim();
            }
        }
        item.name=name;item.needsReview=item.qty.isEmpty()||item.unit.isEmpty();
        return item;
    }
    public static List<Item> parsePlain(String text){
        ArrayList<Item> out=new ArrayList<>();if(text==null)return out;
        int lineNum=0,page=1;
        for(String raw:text.split("\\r?\\n")){
            String line=raw.replaceAll("\\s+"," ").trim();lineNum++;
            if(line.matches("(?i)^--- PAGE \\d+ ---$")){
                Matcher m=Pattern.compile("\\d+").matcher(line);if(m.find())page=Integer.parseInt(m.group());continue;
            }
            if(line.isEmpty()||HEADER.matcher(line).matches()||IGNORE.matcher(line).matches())continue;
            Matcher number=NUMBERED.matcher(line);Item item=new Item();
            if(number.matches()){item.serial=number.group(1);line=number.group(2);}
            Matcher m=QTYUNIT.matcher(line);
            if(m.matches()){item.name=m.group(1);item.qty=m.group(2);item.unit=m.group(3);}
            else item.name=line;
            if(item.name.length()<4||item.name.matches("[\\d.,%/ ]+"))continue;
            item.page=page;item.row=lineNum;item.needsReview=item.qty.isEmpty()||item.unit.isEmpty();out.add(item);
        }
        return out;
    }
    public static List<Item> deduplicate(List<Item> in){
        LinkedHashMap<String,Item> unique=new LinkedHashMap<>();
        for(Item row:in){
            String key=(row.serial+"|"+row.name+"|"+row.qty+"|"+row.unit).toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9|]","");
            // Don't collapse different serials or different tender items with a common name.
            unique.putIfAbsent(key,row);
        }
        return new ArrayList<>(unique.values());
    }
}