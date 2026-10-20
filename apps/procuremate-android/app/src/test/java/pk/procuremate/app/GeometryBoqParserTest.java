package pk.procuremate.app;
import java.util.*;
public final class GeometryBoqParserTest {
 static GeometryBoqParser.Cell c(String s,int x,int y){return new GeometryBoqParser.Cell(s,x,y,x+90,y+15,1);}
 static void assertEquals(String expected,String got){if(!expected.equals(got))throw new AssertionError(expected+" != "+got);}
 static void check(boolean b){if(!b)throw new AssertionError("invalid condition");}
 public static void main(String[] args){
  List<GeometryBoqParser.Cell> geometry=Arrays.asList(
    c("Qty",450,10),c("Article Name",120,10),c("Unit",520,10),c("Sr No",10,10),
    c("5",450,40),c("Dozen",520,40),c("Dettol Surface Cleaner 500ml",120,40),c("1.",10,40),
    c("2",10,70),c("Tissue Paper Party Pack",120,70),c("10",450,70),c("Pack",520,70),
    c("3.",10,100),c("Harpic Liquid 500ml",120,100));
  List<GeometryBoqParser.Item> items=GeometryBoqParser.parse(geometry);
  check(items.size()==3);assertEquals("Dettol Surface Cleaner 500ml",items.get(0).name);
  assertEquals("5",items.get(0).qty);assertEquals("Dozen",items.get(0).unit);
  assertEquals("Tissue Paper Party Pack",items.get(1).name);
  check(!items.get(0).needsReview);check(items.get(2).needsReview);
  check(items.get(2).qty.isEmpty());
  List<GeometryBoqParser.Item> plain=GeometryBoqParser.parsePlain("1. White Paper 3000 Reams\n2. Dettol 500ml\n3. Electric Cattle 5 Nos");
  check(plain.size()==3);assertEquals("White Paper",plain.get(0).name);
  assertEquals("3000",plain.get(0).qty);assertEquals("Dettol 500ml",plain.get(1).name);
  assertEquals("Electric Cattle",plain.get(2).name);
  check(GeometryBoqParser.deduplicate(Arrays.asList(plain.get(0),plain.get(0))).size()==1);
  System.out.println("GeometryBoqParser: all tests passed");
 }
}